"""Interactive LinkedIn login: run once via `make login`.

Opens a visible Chromium window on the LinkedIn login page using the local
persistent profile. As soon as the `li_at` session cookie exists, the session
is stored in the profile and the window closes. Credentials are typed by the
user directly into the browser — they never touch this code.
"""

import asyncio
import time
from pathlib import Path

from patchright.async_api import async_playwright

from app.config import settings

LOGIN_URL = "https://www.linkedin.com/login"
TIMEOUT_SECONDS = 300


async def login() -> None:
    profile_dir = str(Path(settings.linkedin_profile_dir).expanduser())
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    pw = await async_playwright().start()
    context = await pw.chromium.launch_persistent_context(
        user_data_dir=profile_dir,
        headless=False,
    )
    page = context.pages[0] if context.pages else await context.new_page()
    await page.goto(LOGIN_URL, wait_until="domcontentloaded")

    print(f"Faça login no LinkedIn na janela aberta (tempo máximo: {TIMEOUT_SECONDS}s).")
    deadline = time.monotonic() + TIMEOUT_SECONDS
    logged_in = False
    while time.monotonic() < deadline:
        try:
            cookies = await context.cookies("https://www.linkedin.com")
        except Exception:
            break  # window was closed by the user
        if any(cookie.get("name") == "li_at" for cookie in cookies):
            logged_in = True
            break
        await asyncio.sleep(2)

    await context.close()
    await pw.stop()

    if not logged_in:
        raise SystemExit("Login não concluído dentro do tempo. Rode `make login` de novo.")
    print(f"Sessão salva em {profile_dir}. Agora os tools locais funcionam.")


if __name__ == "__main__":
    asyncio.run(login())
