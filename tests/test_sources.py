"""Fase 1 — config and JobSource Protocol are in place and importable."""

import pytest

from app.config import Settings
from app.linkedin.errors import ToolError
from app.sources import (
    JobSource,
    SourceUnavailableError,
    build_sources,
    source_names,
)
from app.sources.linkedin import LinkedInSource


def test_settings_geekhunter_defaults():
    s = Settings(_env_file=None)
    assert s.geekhunter_base_url == "https://www.geekhunter.com"
    assert s.geekhunter_delay_seconds == 1.0
    assert s.geekhunter_page_size == 25
    assert s.geekhunter_timeout_s == 30.0


def test_settings_gupy_defaults():
    s = Settings(_env_file=None)
    assert s.gupy_base_url == "https://portal.gupy.io"
    assert s.gupy_delay_seconds == 1.0
    assert s.gupy_page_size == 10
    assert s.gupy_timeout_s == 30.0


def test_settings_indeed_defaults():
    s = Settings(_env_file=None)
    assert s.indeed_base_url == "https://apis.indeed.com"
    assert s.indeed_delay_seconds == 1.0
    assert s.indeed_page_size == 25
    assert s.indeed_timeout_s == 30.0
    assert s.indeed_max_retries == 2
    assert s.indeed_backoff_seconds == 5.0
    # credential/market live in .env only — never a code default
    assert s.indeed_api_key == ""
    assert s.indeed_country == "BR"
    assert s.indeed_locale == "pt-BR"


def test_settings_sync_defaults():
    s = Settings(_env_file=None)
    assert s.hours_old == 720  # recency window: 30 days (front can override)
    assert s.sync_delay_seconds == 1.0  # politeness pause between sources


def test_settings_glassdoor_defaults():
    s = Settings(_env_file=None)
    assert s.glassdoor_base_url == "https://www.glassdoor.com"
    assert s.glassdoor_delay_seconds == 2.0
    assert s.glassdoor_timeout_ms == 30000
    # headless gets the Cloudflare interstitial on this machine — headful works
    assert s.glassdoor_headless is False


def test_job_source_protocol_surface():
    assert "name" in JobSource.__annotations__
    assert hasattr(JobSource, "search")
    assert hasattr(JobSource, "details")


def test_source_unavailable_is_exception():
    assert issubclass(SourceUnavailableError, Exception)


def test_source_names_lists_every_configured_source():
    config = Settings(_env_file=None)

    assert source_names(config) == ["linkedin", "geekhunter", "gupy", "indeed", "glassdoor"]


def test_source_names_omits_sources_with_an_empty_base_url():
    config = Settings(
        _env_file=None,
        geekhunter_base_url="",
        gupy_base_url="",
        indeed_base_url="",
        glassdoor_base_url="",
    )

    assert source_names(config) == ["linkedin"]


def test_build_sources_registers_the_new_sources():
    config = Settings(_env_file=None)

    registry = build_sources(config)

    assert list(registry) == ["linkedin", "geekhunter", "gupy", "indeed", "glassdoor"]
    assert registry["gupy"].name == "gupy"
    assert registry["indeed"].name == "indeed"
    assert registry["glassdoor"].name == "glassdoor"


def test_build_sources_never_starts_a_browser():
    """Building the registry must stay cheap: /health and sync construct it."""
    config = Settings(_env_file=None)

    registry = build_sources(config)

    # the Glassdoor engine is resolved lazily, only inside search()
    assert registry["glassdoor"]._engine is None


def test_gupy_glassdoor_and_indeed_implement_the_protocol():
    from app.sources.glassdoor import GlassdoorSource
    from app.sources.gupy import GupySource
    from app.sources.indeed import IndeedSource

    # class-level contract: no client is constructed here (no leak, no network)
    for cls in (GupySource, IndeedSource, GlassdoorSource):
        assert cls.name in {"gupy", "indeed", "glassdoor"}
        assert hasattr(cls, "search") and hasattr(cls, "details")


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
