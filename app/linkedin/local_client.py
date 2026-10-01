"""Read-only LinkedIn job access through the local browser session.

Drop-in replacement for the previous MCP adapter: same three methods, same
payload contract (dicts/lists consumed by `app.linkedin.parsing`), no MCP.
"""

from urllib.parse import quote

from app.linkedin.browser import BrowserSession, get_session
from app.linkedin.scrape import parse_job_cards, parse_job_detail

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
SAVED_URL = "https://www.linkedin.com/my-items/saved/jobs/"
DETAIL_URL = "https://www.linkedin.com/jobs/view/{job_id}"
PAGE_SIZE = 25
MAX_PAGES = 9


class LinkedInBrowserClient:
    def __init__(self, session: BrowserSession | None = None) -> None:
        self._session = session or get_session()

    async def search_jobs(self, keywords: str, location: str, limit: int = 25) -> dict:
        jobs: list[dict] = []
        seen: set[str] = set()
        start = 0
        pages = 0
        while len(jobs) < limit and pages < MAX_PAGES:
            url = (
                f"{SEARCH_URL}?keywords={quote(keywords)}&location={quote(location)}&start={start}"
            )
            html = await self._session.fetch(url)
            pages += 1
            fresh = 0
            for item in parse_job_cards(html):
                if item["job_id"] in seen:
                    continue
                seen.add(item["job_id"])
                jobs.append(item)
                fresh += 1
            if fresh == 0:
                break
            start += PAGE_SIZE
        return {"jobs": jobs[:limit]}

    async def get_job_details(self, job_id: str) -> dict:
        html = await self._session.fetch(DETAIL_URL.format(job_id=job_id))
        return parse_job_detail(html, job_id)

    async def get_saved_jobs(self, limit: int = 25) -> dict:
        html = await self._session.fetch(SAVED_URL)
        return {"jobs": parse_job_cards(html)[:limit]}
