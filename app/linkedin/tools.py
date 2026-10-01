"""Local, read-only LinkedIn job tools.

Modeled on the tool catalog of stickerdaniel/linkedin-mcp-server, but scoped to
job reads for this project's MVP and free of any MCP dependency: the backend is
a local browser session (see `app.linkedin.browser`).

Safety: read-only by design — there is intentionally no tool here that writes
to LinkedIn (no messages, no connection requests, no applications).
"""

from typing import Protocol

from pydantic import BaseModel

from app.linkedin.errors import ToolError, ToolNotFoundError
from app.linkedin.local_client import LinkedInBrowserClient
from app.linkedin.parsing import extract_job_items as extract_items


class JobBackend(Protocol):
    async def search_jobs(self, keywords: str, location: str, limit: int = 25) -> object: ...

    async def get_job_details(self, job_id: str) -> object: ...

    async def get_saved_jobs(self, limit: int = 25) -> object: ...


class ToolDescriptor(BaseModel):
    name: str
    description: str
    input_schema: dict


TOOLS: list[ToolDescriptor] = [
    ToolDescriptor(
        name="search_jobs",
        description="Search LinkedIn job postings by keyword and location (read-only).",
        input_schema={
            "type": "object",
            "properties": {
                "keywords": {"type": "string", "minLength": 1},
                "location": {"type": "string", "default": "Brazil"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25},
            },
            "required": ["keywords"],
        },
    ),
    ToolDescriptor(
        name="get_job_details",
        description="Read the details of a LinkedIn job posting by its job ID (read-only).",
        input_schema={
            "type": "object",
            "properties": {"job_id": {"type": "string", "minLength": 1}},
            "required": ["job_id"],
        },
    ),
    ToolDescriptor(
        name="get_saved_jobs",
        description="List job postings you have saved on LinkedIn (read-only).",
        input_schema={
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 25}
            },
        },
    ),
]


class LinkedInTools:
    """Typed wrapper over the read-only backend used by this project."""

    def __init__(self, client: JobBackend | None = None) -> None:
        self._client = client or LinkedInBrowserClient()

    async def search_jobs(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        result = await self._call(
            "search_jobs", self._client.search_jobs(keywords, location, limit)
        )
        return extract_items(result)

    async def get_job_details(self, job_id: str) -> dict:
        result = await self._call("get_job_details", self._client.get_job_details(job_id))
        items = extract_items(result)
        if not items:
            raise ToolNotFoundError(f"job not found: {job_id}")
        return items[0]

    async def get_saved_jobs(self, limit: int = 25) -> list[dict]:
        result = await self._call("get_saved_jobs", self._client.get_saved_jobs(limit))
        return extract_items(result)

    @staticmethod
    async def _call(tool_name: str, awaitable) -> object:
        try:
            return await awaitable
        except ToolError:
            raise
        except Exception as exc:
            raise ToolError(f"{tool_name} failed: {exc}") from exc


def get_tools() -> LinkedInTools:
    return LinkedInTools()
