"""Fase 1 — config and JobSource Protocol are in place and importable."""

import pytest

from app.config import Settings
from app.linkedin.errors import ToolError
from app.sources import JobSource, SourceUnavailableError
from app.sources.linkedin import LinkedInSource


def test_settings_geekhunter_defaults():
    s = Settings(_env_file=None)
    assert s.geekhunter_base_url == "https://www.geekhunter.com"
    assert s.geekhunter_delay_seconds == 1.0
    assert s.geekhunter_page_size == 25
    assert s.geekhunter_timeout_s == 30.0


def test_job_source_protocol_surface():
    assert "name" in JobSource.__annotations__
    assert hasattr(JobSource, "search")
    assert hasattr(JobSource, "details")


def test_source_unavailable_is_exception():
    assert issubclass(SourceUnavailableError, Exception)


class ExpiredSessionClient:
    """LinkedIn client whose session died (`li_at` cookie gone / authwall)."""

    async def search_jobs(self, *args, **kwargs):
        raise ToolError("LinkedIn session not found — run `make login` first")


@pytest.mark.asyncio
async def test_linkedin_tool_error_is_reported_as_source_unavailable():
    """ToolError must not escape sync_jobs: it would 500 the whole request
    and take every other source down with it."""
    source = LinkedInSource(client=ExpiredSessionClient())

    with pytest.raises(SourceUnavailableError, match="make login"):
        await source.search("SRE", "Brazil", 10)
