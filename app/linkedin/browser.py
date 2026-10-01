"""Local Chromium session used for read-only LinkedIn navigation.

The session is a persistent browser profile stored outside the repo
(~/.linkedin-laya/profile by default), created once via `make login`.
All navigations are GET-only; there is no code path that submits forms or
performs write actions on LinkedIn.
"""

import asyncio
from pathlib import Path

from patchright.async_api import async_playwright

from app.config import settings
from app.linkedin.errors import ToolError
from app.linkedin.scrape import is_authwall


class BrowserSession:
    def __init__(
        self,
        profile_dir: str,
        headless: bool = True,
        delay_seconds: float = 1.0,
        timeout_ms: int = 30000,
    ) -> None:
        self.profile_dir = str(Path(profile_dir).expanduser())
        self.headless = headless
        self.delay_seconds = delay_seconds
        self.timeout_ms = timeout_ms
        self._pw = None
        self._context = None
        self._lock = asyncio.Lock()

    async def start(self) -> None:
        if self._context is not None:
            return
        Path(self.profile_dir).mkdir(parents=True, exist_ok=True)
        self._pw = await async_playwright().start()
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=self.profile_dir,
            headless=self.headless,
        )

    async def has_linkedin_session(self) -> bool:
        await self.start()
        cookies = await self._context.cookies("https://www.linkedin.com")
        return any(cookie.get("name") == "li_at" for cookie in cookies)

    async def fetch(self, url: str) -> str:
        """Navigate read-only and return the page HTML.

        Raises ToolError when the user is not logged in or when LinkedIn
        answers with a login wall instead of the requested page.
        """
        if not await self.has_linkedin_session():
            raise ToolError("LinkedIn session not found — run `make login` first")
        async with self._lock:
            page = self._context.pages[0] if self._context.pages else await self._context.new_page()
            await page.goto(url, wait_until="domcontentloaded", timeout=self.timeout_ms)
            if self.delay_seconds:
                await page.wait_for_timeout(int(self.delay_seconds * 1000))
            html = await page.content()
            final_url = page.url
        if is_authwall(final_url, html):
            raise ToolError("LinkedIn showed the login/authwall — run `make login` again")
        return html

    async def stop(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._pw is not None:
            await self._pw.stop()
            self._pw = None


_session: BrowserSession | None = None


def get_session() -> BrowserSession:
    global _session
    if _session is None:
        _session = BrowserSession(
            profile_dir=settings.linkedin_profile_dir,
            headless=settings.linkedin_headless,
            delay_seconds=settings.linkedin_delay_seconds,
            timeout_ms=settings.linkedin_nav_timeout_ms,
        )
    return _session


async def close_session() -> None:
    global _session
    if _session is not None:
        await _session.stop()
        _session = None
