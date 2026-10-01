"""LinkedIn source — browser-backed, read-only.

Thin adapter over the existing `LinkedInBrowserClient` so the sync service
talks to the `JobSource` Protocol instead of a concrete provider.
"""

from app.linkedin.local_client import LinkedInBrowserClient
from app.linkedin.parsing import extract_job_items, merge_job_details


class LinkedInSource:
    name = "linkedin"

    def __init__(self, client: LinkedInBrowserClient | None = None) -> None:
        self._client = client or LinkedInBrowserClient()

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        result = await self._client.search_jobs(keywords, location, limit)
        items = extract_job_items(result)[:limit]
        for item in items:
            item["source"] = self.name
            item["source_id"] = item.pop("linkedin_id", "")
        return items

    async def details(self, item: dict) -> dict:
        """Enrich `item` with the full description (never wipes search data)."""
        try:
            result = await self._client.get_job_details(item["source_id"])
        except Exception:
            # Keep search result when details fail; sync should be partial-success.
            return item
        extracted = extract_job_items(result)
        if not extracted:
            return item
        merge_job_details(item, {"job": extracted[0]})
        return item
