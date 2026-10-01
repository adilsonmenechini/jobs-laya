"""Unit tests for the local LinkedIn tools layer (no network, fake client)."""

import pytest

from app.linkedin.tools import TOOLS, LinkedInTools, ToolError, ToolNotFoundError

SEARCH_PAYLOAD = {
    "jobs": [
        {
            "job_id": "123",
            "title": "Senior SRE",
            "company_name": "Acme",
            "location": "Brazil",
            "workplace_type": "REMOTE",
            "description": "AWS Kubernetes",
        },
        {"job": {"entity_urn": "urn:li:job:456", "job_title": "DevOps Engineer"}},
    ]
}

DETAIL_PAYLOAD = {
    "job": {
        "job_id": "123",
        "title": "Senior SRE",
        "company": "Acme",
        "remote": True,
        "url": "https://linkedin.com/jobs/view/123",
        "description": "Own reliability.",
    }
}


class FakeClient:
    def __init__(self, search=None, detail=None, saved=None, error=None):
        self.search = search
        self.detail = detail
        self.saved = saved
        self.error = error
        self.calls = []

    async def search_jobs(self, keywords, location, limit=25):
        self.calls.append(("search_jobs", keywords, location, limit))
        if self.error:
            raise self.error
        return self.search

    async def get_job_details(self, job_id):
        self.calls.append(("get_job_details", job_id))
        if self.error:
            raise self.error
        return self.detail

    async def get_saved_jobs(self, limit=25):
        self.calls.append(("get_saved_jobs", limit))
        if self.error:
            raise self.error
        return self.saved


def test_registry_exposes_only_read_job_tools():
    names = [tool.name for tool in TOOLS]
    assert names == ["search_jobs", "get_job_details", "get_saved_jobs"]
    for tool in TOOLS:
        assert tool.description
        assert tool.input_schema["type"] == "object"
        assert tool.input_schema["properties"]


@pytest.mark.asyncio
async def test_search_jobs_normalizes_upstream_payload():
    client = FakeClient(search=SEARCH_PAYLOAD)
    tools = LinkedInTools(client=client)

    items = await tools.search_jobs("SRE", "Brazil", limit=2)

    assert client.calls == [("search_jobs", "SRE", "Brazil", 2)]
    assert [item["linkedin_id"] for item in items] == ["123", "456"]
    assert items[0]["title"] == "Senior SRE"
    assert items[0]["remote"] is True
    assert items[1]["title"] == "DevOps Engineer"
    # payloads without an id are dropped, not persisted anywhere
    assert all(item["linkedin_id"] for item in items)


@pytest.mark.asyncio
async def test_search_jobs_accepts_list_payload():
    client = FakeClient(search=[{"job_id": "9", "title": "Platform Engineer"}])
    tools = LinkedInTools(client=client)

    items = await tools.search_jobs("platform", "Brazil")

    assert len(items) == 1
    assert items[0]["linkedin_id"] == "9"


@pytest.mark.asyncio
async def test_get_job_details_returns_single_normalized_item():
    client = FakeClient(detail=DETAIL_PAYLOAD)
    tools = LinkedInTools(client=client)

    item = await tools.get_job_details("123")

    assert item["linkedin_id"] == "123"
    assert item["company"] == "Acme"
    assert item["remote"] is True
    assert item["url"] == "https://linkedin.com/jobs/view/123"


@pytest.mark.asyncio
async def test_get_job_details_missing_payload_raises_not_found():
    client = FakeClient(detail={"jobs": []})
    tools = LinkedInTools(client=client)

    with pytest.raises(ToolNotFoundError):
        await tools.get_job_details("nope")


@pytest.mark.asyncio
async def test_get_saved_jobs_normalizes():
    client = FakeClient(saved={"results": [{"id": "77", "title": "Staff SRE"}]})
    tools = LinkedInTools(client=client)

    items = await tools.get_saved_jobs(limit=5)

    assert client.calls == [("get_saved_jobs", 5)]
    assert items[0]["linkedin_id"] == "77"


@pytest.mark.asyncio
async def test_client_errors_are_wrapped_as_tool_error():
    client = FakeClient(error=RuntimeError("browser not ready"))
    tools = LinkedInTools(client=client)

    with pytest.raises(ToolError, match="browser not ready"):
        await tools.search_jobs("SRE", "Brazil")
