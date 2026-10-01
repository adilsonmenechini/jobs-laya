"""LinkedInBrowserClient tests with a fake browser session (no browser, no network)."""

import pytest

from app.linkedin.errors import ToolError
from app.linkedin.local_client import LinkedInBrowserClient
from tests.fixtures_loader import fixture


class FakeSession:
    def __init__(self, pages: dict[str, str], logged_in: bool = True):
        self.pages = pages
        self.logged_in = logged_in
        self.visited: list[str] = []

    async def fetch(self, url: str) -> str:
        self.visited.append(url)
        if not self.logged_in:
            raise ToolError("LinkedIn session not found — run `make login` first")
        for prefix, html in self.pages.items():
            if url.startswith(prefix):
                return html
        return "<html>empty</html>"


@pytest.mark.asyncio
async def test_search_jobs_returns_parsed_payload_with_limit():
    session = FakeSession({"https://www.linkedin.com/jobs-guest/": fixture("search_cards.html")})
    client = LinkedInBrowserClient(session=session)

    result = await client.search_jobs("SRE", "Brazil", limit=1)

    assert len(result["jobs"]) == 1
    assert result["jobs"][0]["job_id"] == "3987654321"
    assert "keywords=SRE" in session.visited[0]
    assert "location=Brazil" in session.visited[0]


@pytest.mark.asyncio
async def test_search_jobs_stops_when_upstream_returns_no_new_results():
    session = FakeSession({"https://www.linkedin.com/jobs-guest/": fixture("search_cards.html")})
    client = LinkedInBrowserClient(session=session)

    result = await client.search_jobs("SRE", "Brazil", limit=50)

    # same page forever -> dedupe stops pagination after the first new batch
    assert len(result["jobs"]) == 2
    assert len(session.visited) == 2


@pytest.mark.asyncio
async def test_get_job_details_parses_detail_page():
    session = FakeSession({"https://www.linkedin.com/jobs/view/": fixture("job_detail.html")})
    client = LinkedInBrowserClient(session=session)

    item = await client.get_job_details("3987654321")

    assert item["job_id"] == "3987654321"
    assert item["title"] == "Senior SRE"
    assert item["remote"] is True


@pytest.mark.asyncio
async def test_get_saved_jobs_uses_my_items_page():
    session = FakeSession({"https://www.linkedin.com/my-items/": fixture("saved_jobs.html")})
    client = LinkedInBrowserClient(session=session)

    result = await client.get_saved_jobs(limit=10)

    assert result["jobs"][0]["job_id"] == "1122556677"
    assert result["jobs"][0]["title"] == "Staff Platform Engineer"
    assert session.visited[0].startswith("https://www.linkedin.com/my-items/saved/jobs")


@pytest.mark.asyncio
async def test_client_propagates_missing_session_error():
    session = FakeSession({}, logged_in=False)
    client = LinkedInBrowserClient(session=session)

    with pytest.raises(ToolError, match="make login"):
        await client.search_jobs("SRE", "Brazil")
