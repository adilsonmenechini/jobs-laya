"""Gupy source — public HTTP, read-only, no login and no browser.

The portal exposes an open JSON API (`/api/job-search/jobs`) that already
returns the full description, so details() only runs when the search payload
came without one: it fetches the SSR job page and reads the description out
of `__NEXT_DATA__`.

Defense: configurable delay between page fetches, explicit timeout and an
identifiable User-Agent (`settings.gupy_*`).
"""

import asyncio
import json
import re
from html import unescape

import httpx
from bs4 import BeautifulSoup

from app.config import Settings, settings
from app.sources.base import SourceUnavailableError
from app.sources.retry import retry_on_transient

SEARCH_PATH = "/api/job-search/jobs"
TEXT_CLEAN = re.compile(r"\s+")
NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)

# Full state name → UF, and the 27 states accepted as a `state=` filter.
STATE_UF = {
    "Acre": "AC",
    "Alagoas": "AL",
    "Amapá": "AP",
    "Amazonas": "AM",
    "Bahia": "BA",
    "Ceará": "CE",
    "Distrito Federal": "DF",
    "Espírito Santo": "ES",
    "Goiás": "GO",
    "Maranhão": "MA",
    "Mato Grosso": "MT",
    "Mato Grosso do Sul": "MS",
    "Minas Gerais": "MG",
    "Pará": "PA",
    "Paraíba": "PB",
    "Paraná": "PR",
    "Pernambuco": "PE",
    "Piauí": "PI",
    "Rio de Janeiro": "RJ",
    "Rio Grande do Norte": "RN",
    "Rio Grande do Sul": "RS",
    "Rondônia": "RO",
    "Roraima": "RR",
    "Santa Catarina": "SC",
    "São Paulo": "SP",
    "Sergipe": "SE",
    "Tocantins": "TO",
}
NATIONAL = {"brazil", "brasil"}
REMOTE = {"remoto", "remote"}


def location_params(location: str) -> dict[str, str]:
    """Map a user location to the API's filter params.

    Gotchas handled here: "remoto" must become `workplaceType`, never `city`;
    only the 27 full state names become `state=`; everything else is a city.
    """
    value = (location or "").strip()
    if not value or value.casefold() in NATIONAL:
        return {}
    if value.casefold() in REMOTE:
        return {"workplaceType": "remote"}
    for state in STATE_UF:
        if state.casefold() == value.casefold():
            return {"state": state}
    return {"city": value}


def clean_text(value: str | None) -> str:
    """Plain text with HTML entities decoded and whitespace collapsed."""
    if not value:
        return ""
    text = unescape(value).replace("\xa0", " ")
    return TEXT_CLEAN.sub(" ", text).strip()


def _location(city: str | None, state: str | None) -> str:
    city = (city or "").strip()
    state = (state or "").strip()
    if city and state:
        return f"{city} - {STATE_UF.get(state, state)}"
    return city or STATE_UF.get(state, state)


def normalize_item(payload: dict) -> dict:
    """One API item → normalized job item (JobSource contract)."""
    published = payload.get("publishedDate") or None
    return {
        "source": "gupy",
        "source_id": str(payload.get("id", "")),
        "title": payload.get("name") or "",
        "company": payload.get("careerPageName") or None,
        "location": _location(payload.get("city"), payload.get("state")),
        "remote": payload.get("workplaceType") == "remote",
        "url": payload.get("jobUrl") or None,
        "description": clean_text(payload.get("description")),
        # Job.posted_at is String(100): never let a longer date overflow it.
        "posted_at": published[:100] if published else None,
        "raw": payload,
    }


def parse_search(payload: dict) -> list[dict]:
    return [normalize_item(item) for item in payload.get("data") or []]


def parse_detail(page: str) -> str | None:
    """SSR job page → the full description from `__NEXT_DATA__` (None if absent)."""
    match = NEXT_DATA.search(page)
    if not match:
        return None
    try:
        job = json.loads(match.group(1))["props"]["pageProps"]["job"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return None
    description = job.get("description")
    if not description:
        return None
    text = BeautifulSoup(description, "html.parser").get_text(" ", strip=True)
    return clean_text(text) or None


class GupySource:
    name = "gupy"

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or settings
        self._client = client or httpx.AsyncClient(
            base_url=self._config.gupy_base_url,
            timeout=self._config.gupy_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": "job-classifier/0.1.0 (job research; read-only)"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _fetch(self, url: str, params: dict | None = None) -> httpx.Response:
        try:
            response = await retry_on_transient(
                lambda: self._client.get(url, params=params),
                max_retries=self._config.gupy_max_retries,
                backoff_seconds=self._config.gupy_backoff_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"gupy request failed: {exc}") from exc
        return response

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        page_size = max(1, self._config.gupy_page_size)
        filters = location_params(location)
        items: list[dict] = []
        offset = 0
        while len(items) < limit:
            response = await self._fetch(
                SEARCH_PATH,
                {"jobName": keywords, "limit": page_size, "offset": offset, **filters},
            )
            try:
                payload = response.json()
            except ValueError as exc:
                raise SourceUnavailableError(f"gupy returned non-JSON: {exc}") from exc
            batch = parse_search(payload)
            if not batch:
                break
            items.extend(batch)
            if len(batch) < page_size:
                break  # last page
            offset += page_size
            if self._config.gupy_delay_seconds:
                await asyncio.sleep(self._config.gupy_delay_seconds)
        return items[:limit]

    async def details(self, item: dict) -> dict:
        """Enrich `item` with the description when the search payload lacked one."""
        if item.get("description"):
            return item
        url = item.get("url")
        if not url:
            return item
        response = await self._fetch(url)
        description = parse_detail(response.text)
        if description:
            item["description"] = description
        return item
