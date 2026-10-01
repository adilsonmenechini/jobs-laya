"""Fase 1 — config and JobSource Protocol are in place and importable."""

from app.config import Settings
from app.sources import JobSource, SourceUnavailableError


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
