"""Glassdoor source — browser-backed, read-only (HTTP is Cloudflare-403).

The SERP is fetched through an injectable engine (`goto`/`wait`/`evaluate`)
so tests run against the real fixture without launching a browser. All
detail routes are challenge-blocked in the local headless/headful Chromium
(spec Non-Goals), therefore `details()` is a documented no-op: v1 stores the
snippet + skills line returned by the SERP.

Defense: configurable delay between navigations, explicit timeout, and a
recognizable Cloudflare interstitial ("Um momento…" / "Somente humanos")
surfaced as `SourceUnavailableError` so the sync degrades this source only.
"""

import asyncio
import html
from typing import Protocol
from urllib.parse import parse_qs, quote, urlparse

from bs4 import BeautifulSoup

from app.config import Settings, settings
from app.sources.base import SourceUnavailableError

SERP_PATH = "/Job/jobs.htm"
CARDS_SELECTOR = 'li[data-test="jobListing"]'
TITLE_SCRIPT = "() => document.title"
HTML_SCRIPT = "() => document.documentElement.outerHTML"
CHALLENGE_TITLES = ("um momento", "somente humanos", "just a moment", "checking your browser")


class GlassdoorEngine(Protocol):
    """Minimal browser surface the source needs (fakeable in tests)."""

    async def goto(self, url: str) -> None: ...

    async def wait(self, selector: str) -> None: ...

    async def evaluate(self, script: str) -> str: ...


def is_challenge(title: str | None) -> bool:
    """True when Cloudflare answered instead of the SERP."""
    normalized = (title or "").strip().casefold()
    return any(marker in normalized for marker in CHALLENGE_TITLES)


def _source_id(url: str) -> str:
    query = parse_qs(urlparse(url).query)
    if query.get("jl"):
        return query["jl"][0]
    slug = urlparse(url).path.rstrip("/").rsplit("/", 1)[-1]
    return slug.removesuffix(".htm")


def _text(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def _description(card) -> str:
    """Snippet + the `Habilidades:` line, entities decoded."""
    snippet = card.select_one('[data-test="descSnippet"]')
    if not snippet:
        return ""
    return html.unescape(_text(snippet))


def parse_serp(page: str) -> list[dict]:
    """Rendered SERP → normalized items (class-hash independent selectors)."""
    soup = BeautifulSoup(page, "html.parser")
    items: list[dict] = []
    for card in soup.select(CARDS_SELECTOR):
        anchor = card.select_one('a[data-test="job-title"]')
        if anchor is None or not anchor.get("href"):
            continue
        salary = _text(card.select_one('[class*="salaryEstimate"]'))
        items.append(
            {
                "source": "glassdoor",
                "source_id": _source_id(anchor["href"]),
                "title": _text(anchor),
                "company": _text(card.select_one('[class*="compactEmployerName"]')) or None,
                "location": _text(card.select_one('[data-test="emp-location"]')) or None,
                # No trustworthy remote badge on the SERP: keep False (spec FR-2).
                "remote": False,
                "url": anchor["href"],
                "description": _description(card),
                "posted_at": None,
                "raw": {"salary": salary or None},
            }
        )
    return items


class PatchrightGlassdoorEngine:
    """Real engine: one persistent local Chromium via Patchright."""

    def __init__(self, headless: bool, timeout_ms: int, delay_seconds: float) -> None:
        self._headless = headless
        self._timeout_ms = timeout_ms
        self._delay_seconds = delay_seconds
        self._pw = None
        self._context = None
        self._page = None

    async def _ensure(self) -> None:
        if self._page is not None:
            return
        from patchright.async_api import async_playwright  # noqa: PLC0415

        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch(headless=self._headless)
        self._page = await self._context.new_page()

    async def goto(self, url: str) -> None:
        await self._ensure()
        await self._page.goto(url, wait_until="domcontentloaded", timeout=self._timeout_ms)
        if self._delay_seconds:
            await self._page.wait_for_timeout(int(self._delay_seconds * 1000))

    async def wait(self, selector: str) -> None:
        await self._page.wait_for_selector(selector, timeout=self._timeout_ms)

    async def evaluate(self, script: str) -> str:
        return await self._page.evaluate(script)

    async def close(self) -> None:
        # Shutdown must never raise nor leave a coroutine un-awaited.
        if self._context is not None:
            try:
                await self._context.close()
            except Exception:  # noqa: BLE001
                pass
        if self._pw is not None:
            try:
                # `stop` is the context manager's __aexit__ (see patchright).
                await self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
        self._page = self._context = self._pw = None


class GlassdoorSource:
    name = "glassdoor"

    def __init__(
        self, config: Settings | None = None, engine: GlassdoorEngine | None = None
    ) -> None:
        self._config = config or settings
        # Built lazily inside search(): constructing the registry must be cheap.
        self._engine = engine
        self._owns_engine = engine is None

    def _build_engine(self) -> GlassdoorEngine:
        return PatchrightGlassdoorEngine(
            headless=self._config.glassdoor_headless,
            timeout_ms=self._config.glassdoor_timeout_ms,
            delay_seconds=0.0,  # the source owns the inter-navigation delay
        )

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        # `location` is ignored on purpose: the SERP covers all of Brazil (spec FR-2).
        url = f"{self._config.glassdoor_base_url}{SERP_PATH}?sc.keyword={quote(keywords)}"
        engine = self._engine or self._build_engine()
        try:
            await engine.goto(url)
            title = await engine.evaluate(TITLE_SCRIPT)
            if is_challenge(title):
                # Fail fast: waiting for cards on a challenge page wastes the timeout.
                raise SourceUnavailableError(f"glassdoor challenge page: {title!r}")
            await engine.wait(CARDS_SELECTOR)
            page = await engine.evaluate(HTML_SCRIPT)
        except SourceUnavailableError:
            raise
        except Exception as exc:
            raise SourceUnavailableError(f"glassdoor navigation failed: {exc}") from exc
        finally:
            if self._owns_engine and engine is not self._engine:
                # One Chromium per search(): never leak a browser process.
                await engine.close()  # type: ignore[attr-defined]
        if self._config.glassdoor_delay_seconds:
            await asyncio.sleep(self._config.glassdoor_delay_seconds)
        return parse_serp(page)[:limit]

    async def details(self, item: dict) -> dict:
        """No-op by design: every detail route is Cloudflare-blocked (spec Non-Goals).

        Never raises, so a broken browser cannot fail an otherwise good sync.
        """
        return item
