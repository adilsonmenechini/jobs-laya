"""Read-only job sources. See `app.sources.base` for the Protocol."""

from app.config import Settings, settings
from app.sources.base import JobSource, SourceUnavailableError
from app.sources.linkedin import LinkedInSource


def source_names(config: Settings | None = None) -> list[str]:
    """Configured source names without constructing any client.

    Used by `/health` (polled every 30s by the dashboard): building real
    sources there would open an httpx client per call and leak sockets.
    """
    cfg = config or settings
    names = ["linkedin"]
    if cfg.geekhunter_base_url:
        names.append("geekhunter")
    if cfg.gupy_base_url:
        names.append("gupy")
    if cfg.indeed_base_url:
        names.append("indeed")
    if cfg.glassdoor_base_url:
        names.append("glassdoor")
    return names


def build_sources(config: Settings | None = None) -> dict[str, JobSource]:
    """Registry of configured sources.

    Pattern from gkhr-interview-assistant (`createApp(config, dependencies)`):
    providers are constructed from config and injected, so tests (and future
    callers) can substitute fakes. A source missing here raises
    `SourceUnavailableError` instead of silently syncing another provider.
    """
    cfg = config or settings
    sources: dict[str, JobSource] = {"linkedin": LinkedInSource()}
    if cfg.geekhunter_base_url:
        from app.sources.geekhunter import GeekHunterSource  # noqa: PLC0415

        sources["geekhunter"] = GeekHunterSource(cfg)
    if cfg.gupy_base_url:
        from app.sources.gupy import GupySource  # noqa: PLC0415

        sources["gupy"] = GupySource(cfg)
    if cfg.indeed_base_url:
        from app.sources.indeed import IndeedSource  # noqa: PLC0415

        sources["indeed"] = IndeedSource(cfg)
    if cfg.glassdoor_base_url:
        from app.sources.glassdoor import GlassdoorSource  # noqa: PLC0415

        # Browser engine stays None until search(): /health and build_sources
        # must remain cheap and never launch Chromium.
        sources["glassdoor"] = GlassdoorSource(cfg)
    return sources


def get_sources() -> dict[str, JobSource]:
    return build_sources()


__all__ = [
    "GeekHunterSource",
    "JobSource",
    "SourceUnavailableError",
    "build_sources",
    "get_sources",
    "source_names",
]
