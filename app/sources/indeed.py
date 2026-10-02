"""Indeed source — public GraphQL endpoint, read-only, no login and no browser.

The HTML SERP is a dead end for this project: it carries neither the
description nor the posting date, and the classifier scores both. The open
JSON endpoint (`apis.indeed.com/graphql`, the same one JobSpy drives) returns
title, employer, location, the full description HTML, the skill attributes and
the employer's apply URL in a single request.

Defense: configurable delay between page fetches, explicit timeout, transport
retries with exponential backoff + jitter (`indeed_max_retries` /
`indeed_backoff_seconds`) and an identifiable client (`settings.indeed_*`).
Credential and market come from `.env` (`INDEED_API_KEY`, `INDEED_CO`,
`INDEED_LOCALE`) — never from code; without a key the source refuses to fire.
"""

import asyncio
import random
import re
from datetime import datetime
from html import unescape

import httpx
from bs4 import BeautifulSoup

from app.config import Settings, settings
from app.sources.base import SourceUnavailableError

GRAPHQL_PATH = "/graphql"
TEXT_CLEAN = re.compile(r"\s+")
REMOTE_MARKERS = ("remoto", "remote")

# Trimmed to the fields the classifier uses: a full employer dossier doubles
# the payload for data nothing reads.
QUERY = """
query GetJobData {{
  jobSearch(
  what: "{what}"
  {location}
  limit: {limit}
  {cursor}
  sort: RELEVANCE
  ) {{
  pageInfo {{ nextCursor }}
  results {{
    trackingKey
    job {{
      key
      title
      datePublished
      dateOnIndeed
      description {{ html }}
      location {{ city admin1Code countryCode formatted {{ short long }} }}
      compensation {{
        currencyCode
        baseSalary {{ unitOfWork range {{ ... on Range {{ min max }} }} }}
      }}
      attributes {{ key label }}
      employer {{ name relativeCompanyPageUrl }}
      recruit {{ viewJobUrl detailedSalary }}
    }}
  }}
  }}
}}
"""

# Identity strings of the official mobile client — not credentials, so they
# stay in code; the credential and the market come from settings (.env).
CLIENT_HEADERS = {
    "content-type": "application/json",
    "accept": "application/json",
    "user-agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6_1 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 Indeed App 193.1"
    ),
    "indeed-app-info": "appv=193.1; appid=com.indeed.jobsearch; osv=16.6.1; os=ios; dtype=phone",
}


def api_headers(config: Settings) -> dict:
    """Credential + market headers; refuses to fire without a key.

    The key (public, shipped inside the official app) still lives in `.env`
    as `INDEED_API_KEY` so rotating it never touches code — a hardcoded
    secret is exactly what `.env` exists to avoid. `INDEED_CO` /
    `INDEED_LOCALE` pick the market: without them Indeed answers the wrong
    country.
    """
    if not config.indeed_api_key:
        raise SourceUnavailableError("indeed api key not configured — set INDEED_API_KEY in .env")
    return {
        **CLIENT_HEADERS,
        "indeed-api-key": config.indeed_api_key,
        "indeed-co": config.indeed_country,
        "indeed-locale": config.indeed_locale,
    }


def location_arg(location: str) -> str:
    """User location → the `where:` clause (empty = national search).

    "Remoto" is a real Indeed location value on the BR site, so it travels in
    `where:` like any city — it is not a keyword filter.
    """
    value = (location or "").strip()
    if not value or value.casefold() in {"brazil", "brasil"}:
        return ""
    if value.casefold() in {"remoto", "remote"}:
        return "remoto"
    return value


def strip_html(value: str | None) -> str:
    """HTML fragment → plain text with entities decoded and spaces collapsed."""
    if not value:
        return ""
    text = BeautifulSoup(value, "html.parser").get_text(" ", strip=True)
    return TEXT_CLEAN.sub(" ", unescape(text)).strip()


def _posted_at(job: dict) -> str | None:
    """Epoch millis → `YYYY-MM-DD` (Job.posted_at is String(100))."""
    # dateOnIndeed is when the job landed on Indeed; datePublished is the
    # employer's own date and can be older — prefer the fresher signal.
    stamp = job.get("dateOnIndeed") or job.get("datePublished")
    if not isinstance(stamp, (int, float)) or stamp <= 0:
        return None
    return datetime.fromtimestamp(stamp / 1000).strftime("%Y-%m-%d")


def _location(job: dict) -> str | None:
    formatted = (job.get("location") or {}).get("formatted") or {}
    return formatted.get("short") or formatted.get("long") or None


def _is_remote(job: dict) -> bool:
    """Indeed BR marks remote postings with a city of "Remoto"."""
    location = _location(job) or ""
    return any(marker in location.casefold() for marker in REMOTE_MARKERS)


def _url(job: dict) -> str | None:
    view_url = (job.get("recruit") or {}).get("viewJobUrl")
    if view_url:
        return view_url
    key = job.get("key")
    # Without an employer link the Indeed viewjob page is the only stable home.
    return f"https://br.indeed.com/viewjob?jk={key}" if key else None


def normalize_item(job: dict) -> dict:
    """One GraphQL job → normalized job item (JobSource contract)."""
    employer = job.get("employer") or {}
    attributes = job.get("attributes") or []
    compensation = job.get("compensation") or {}
    salary = compensation.get("baseSalary") or {}
    rng = (salary.get("range") or {}) if isinstance(salary, dict) else {}
    return {
        "source": "indeed",
        "source_id": str(job.get("key") or ""),
        "title": job.get("title") or "",
        "company": employer.get("name") or None,
        "location": _location(job),
        "remote": _is_remote(job),
        "url": _url(job),
        "description": strip_html((job.get("description") or {}).get("html")),
        "posted_at": _posted_at(job),
        "raw": {
            "key": job.get("key"),
            "skills": [a.get("label") for a in attributes if a.get("label")],
            "currency": compensation.get("currencyCode"),
            "min_amount": rng.get("min"),
            "max_amount": rng.get("max"),
            "unit_of_work": salary.get("unitOfWork") if isinstance(salary, dict) else None,
            "date_published": job.get("datePublished"),
        },
    }


def parse_response(payload: dict) -> list[dict]:
    """GraphQL response → normalized items ([] when the answer is an error)."""
    search = (payload.get("data") or {}).get("jobSearch") if payload else None
    if not search:
        return []
    return [normalize_item(result["job"]) for result in search.get("results") or []]


def _next_cursor(payload: dict) -> str | None:
    search = (payload.get("data") or {}).get("jobSearch") if payload else None
    if not search:
        return None
    return (search.get("pageInfo") or {}).get("nextCursor") or None


class IndeedSource:
    name = "indeed"

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or settings
        self._client = client or httpx.AsyncClient(
            base_url=self._config.indeed_base_url,
            timeout=self._config.indeed_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": "job-classifier/0.1.0 (job research; read-only)"},
        )

    def _build_query(self, keywords: str, location: str, limit: int, cursor: str | None) -> str:
        where = location_arg(location)
        location_clause = (
            f'location: {{where: "{where}", radius: 50, radiusUnit: MILES}}' if where else ""
        )
        return QUERY.format(
            what=(keywords or "").replace('"', '\\"'),
            location=location_clause,
            limit=limit,
            cursor=f'cursor: "{cursor}"' if cursor else "",
        )

    async def _post(self, query: str) -> dict:
        headers = api_headers(self._config)  # config error → never retried
        attempts = 1 + max(0, self._config.indeed_max_retries)
        backoff = max(0.0, self._config.indeed_backoff_seconds)
        for attempt in range(attempts):
            try:
                response = await self._client.post(
                    GRAPHQL_PATH, headers=headers, json={"query": query}
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                # Transport failures are the only transient class here. The
                # last attempt reports them as unavailable so one flaky page
                # degrades this source instead of the whole sync.
                if attempt >= attempts - 1:
                    raise SourceUnavailableError(f"indeed request failed: {exc}") from exc
                # Exponential backoff + jitter: identical retry timing across
                # clients is what turns a blip into a ban.
                await asyncio.sleep(backoff * (2**attempt) + random.uniform(0.0, backoff))
                continue
            try:
                payload = response.json()
            except ValueError as exc:
                # Permanent by nature (captive portal, HTML shell) — no retry.
                raise SourceUnavailableError(f"indeed returned non-JSON: {exc}") from exc
            if payload.get("errors"):
                # The endpoint answered: retrying cannot change an auth or
                # validation error, so surface it on the first response.
                message = "; ".join(
                    str(err.get("message")) for err in payload["errors"] if isinstance(err, dict)
                )
                detail = message or str(payload["errors"])
                raise SourceUnavailableError(f"indeed graphql error: {detail}")
            return payload

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        page_size = max(1, self._config.indeed_page_size)
        items: list[dict] = []
        cursor: str | None = None
        while len(items) < limit:
            payload = await self._post(self._build_query(keywords, location, page_size, cursor))
            batch = parse_response(payload)
            if not batch:
                break
            items.extend(batch)
            cursor = _next_cursor(payload)
            if not cursor:
                break  # last page
            if self._config.indeed_delay_seconds:
                await asyncio.sleep(self._config.indeed_delay_seconds)
        return items[:limit]

    async def details(self, item: dict) -> dict:
        """No-op by design: the GraphQL search already returns the full
        description, so there is nothing left to fetch.

        Never raises, so a flaky upstream cannot fail an otherwise good sync.
        """
        return item
