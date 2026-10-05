"""GeekHunter source — public HTTP, read-only, no login and no browser.

The listing (`/pt/vagas`) and the job pages are server-rendered and carry
structured data (`ItemList` / `JobPosting` JSON-LD), so parsing goes for
JSON-LD first and falls back to the rendered DOM (cards / `#job-details`).

Defense: configurable delay between page fetches, explicit timeout and a
identifiable User-Agent (`settings.geekhunter_*`).
"""

import asyncio
import json
import re
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import Settings, settings
from app.sources.base import SourceUnavailableError
from app.sources.retry import retry_on_transient

MODALITY_LABELS = {"Remoto", "Híbrido", "Presencial"}
SENIORITY_LABELS = {
    "Estágio",
    "Júnior",
    "Junior",
    "Assistente",
    "Pleno",
    "Sênior",
    "Senior",
    "Líder/Coordenador",
    "Gerente",
    "Diretor",
    "Executivo",
}
SKILL_OVERFLOW = re.compile(r"^\+\d+$")
JOB_PATH = re.compile(r"/pt/([^/]+)/jobs/([^/?#]+)")
TEXT_CLEAN = re.compile(r"\s+")


def _source_id(url: str) -> str:
    """Normalized path as the id — the slug alone collides across companies.

    Job slugs end with a per-company counter (`sre--senior-1`), so two
    employers can mint the same slug: as a bare slug they overwrite each
    other in `parse_search_page` and in the DB upsert.
    """
    return urlparse(url).path.rstrip("/")


def _identifier_value(posting: dict) -> str | None:
    """GeekHunter's internal job id (JSON-LD `identifier.value`).

    A content-independent hash: unlike the URL slug, it survives an upstream
    slug rename, so the upsert matches the same row instead of adding one.
    """
    identifier = posting.get("identifier")
    value = identifier.get("value") if isinstance(identifier, dict) else None
    return value if isinstance(value, str) and value else None


def _detail_source_id(posting: dict, url: str) -> str:
    """Stable id for the detail payload: internal id when present, else path."""
    return _identifier_value(posting) or _source_id(url)


def _company_slug(url: str) -> str | None:
    match = JOB_PATH.search(url)
    return match.group(1) if match else None


def normalize_modality(label: str | None) -> bool:
    """GeekHunter modality badge → the Job `remote` flag."""
    return label == "Remoto"


def _json_ld_blocks(soup: BeautifulSoup) -> list[dict]:
    blocks = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or script.get_text() or "")
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(data, dict):
            blocks.append(data)
    return blocks


def _parse_card(node) -> dict | None:
    """One `<li id="job-…">` card → normalized item (class-hash independent)."""
    anchor = node.find("a", href=JOB_PATH)
    if anchor is None:
        return None
    url = anchor["href"]
    texts = [p.get_text(" ", strip=True) for p in node.find_all("p")]

    modality = next((t for t in texts if t in MODALITY_LABELS), None)
    seniority = next((t for t in texts if t in SENIORITY_LABELS), None)
    description = ""
    if "Tarefas e Responsabilidades" in texts:
        index = texts.index("Tarefas e Responsabilidades")
        if index + 1 < len(texts):
            description = texts[index + 1]
    skills: list[str] = []
    if "Requisitos" in texts:
        index = texts.index("Requisitos")
        skills = [t for t in texts[index + 1 :] if not SKILL_OVERFLOW.match(t)]

    return {
        "source": "geekhunter",
        "source_id": _source_id(url),
        "title": anchor.get_text(" ", strip=True),
        "company": None,  # only the detail page carries the company name
        "company_slug": _company_slug(url),
        "location": next(
            (t for t in texts if t.endswith("Brasil") or re.match(r"^.+, [A-Z]{2}$", t)),
            None,
        ),
        "remote": normalize_modality(modality),
        "url": url,
        "description": description,
        "posted_at": next((t for t in texts if t.startswith(("Publicada", "Atualizada"))), None),
        "modality": modality,
        "seniority": seniority,
        "skills": skills,
        "raw": {"modality": modality, "seniority": seniority, "skills": skills},
    }


def parse_search_page(html: str) -> list[dict]:
    """Listing page → normalized items.

    JSON-LD `ItemList` is authoritative for order/title/url; the rendered
    cards enrich with modality, location, excerpt and skills.
    """
    soup = BeautifulSoup(html, "html.parser")
    items: dict[str, dict] = {}

    for block in _json_ld_blocks(soup):
        if block.get("@type") != "ItemList":
            continue
        for entry in block.get("itemListElement") or []:
            url = entry.get("url") if isinstance(entry, dict) else None
            if not url:
                continue
            source_id = _source_id(url)
            items[source_id] = {
                "source": "geekhunter",
                "source_id": source_id,
                "title": entry.get("name") or "",
                "company": None,
                "company_slug": _company_slug(url),
                "location": None,
                "remote": False,
                "url": url,
                "description": "",
                "posted_at": None,
                "raw": {},
            }

    for node in soup.find_all("li", id=re.compile(r"^job-")):
        card = _parse_card(node)
        if card and card["source_id"] in items:
            items[card["source_id"]].update(card)
        elif card:
            items[card["source_id"]] = card

    return list(items.values())


def parse_job_detail(html: str) -> dict:
    """Job page → normalized item with the full description.

    Prefers the `JobPosting` JSON-LD; falls back to `h1` + `#job-details`.
    Raises `KeyError` when neither source yields a job.
    """
    soup = BeautifulSoup(html, "html.parser")

    posting = next((b for b in _json_ld_blocks(soup) if b.get("@type") == "JobPosting"), None)
    if posting:
        url = posting.get("url") or ""
        description_html = posting.get("description") or ""
        description = BeautifulSoup(description_html, "html.parser").get_text(" ", strip=True)
        remote = posting.get("jobLocationType") == "TELECOMMUTE"
        org = posting.get("hiringOrganization") or {}
        skills = posting.get("skills") or ""
        return {
            "source": "geekhunter",
            "source_id": _detail_source_id(posting, url),
            "title": posting.get("title") or "",
            "company": org.get("name") if isinstance(org, dict) else None,
            "company_slug": _company_slug(url),
            "location": None,
            "remote": remote,
            "modality": "Remoto" if remote else None,
            "url": url,
            "description": description,
            "posted_at": posting.get("datePosted"),
            "skills": [s.strip() for s in skills.split(",") if s.strip()],
            "raw": posting,
        }

    heading = soup.find("h1")
    if heading is None:
        raise KeyError("no job found: missing JobPosting JSON-LD and <h1>")
    text = soup.get_text(" ", strip=True)
    details = soup.find(id="job-details")
    remote = "Remoto" in text
    return {
        "source": "geekhunter",
        "source_id": None,
        "title": heading.get_text(" ", strip=True),
        "company": None,
        "company_slug": None,
        "location": None,
        "remote": remote,
        "modality": "Remoto" if remote else None,
        "url": None,
        "description": details.get_text(" ", strip=True) if details else "",
        "posted_at": None,
        "skills": [],
        "raw": {},
    }


def merge_detail(item: dict, detail: dict) -> dict:
    """Merge a detail payload without destroying good search data.

    Only non-empty detail fields overwrite; `remote` only ever upgrades to
    True (a detail page cannot prove the listing badge was on-site).
    """
    for key, value in detail.items():
        if key == "raw":
            item["raw"] = {**(item.get("raw") or {}), "detail": value}
        elif key == "remote":
            item["remote"] = bool(item.get("remote")) or bool(value)
        elif value not in (None, "", []):
            item[key] = value
    return item


class GeekHunterSource:
    name = "geekhunter"

    def __init__(
        self,
        config: Settings | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config or settings
        self._client = client or httpx.AsyncClient(
            base_url=self._config.geekhunter_base_url,
            timeout=self._config.geekhunter_timeout_s,
            follow_redirects=True,
            headers={"User-Agent": "job-classifier/0.1.0 (job research; read-only)"},
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _get(self, url: str, params: dict | None = None) -> str:
        try:
            response = await retry_on_transient(
                lambda: self._client.get(url, params=params),
                max_retries=self._config.geekhunter_max_retries,
                backoff_seconds=self._config.geekhunter_backoff_seconds,
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise SourceUnavailableError(f"geekhunter request failed: {exc}") from exc
        return response.text

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        params: dict[str, str | int] = {"searchTerm": keywords}
        city = (location or "").strip()
        # cityName is matched verbatim upstream: only send real cities.
        if city and city.lower() not in {"brazil", "brasil"}:
            params["cityName"] = city

        page_size = max(1, self._config.geekhunter_page_size)
        items: list[dict] = []
        page = 1
        while len(items) < limit:
            html = await self._get("/pt/vagas", {**params, "page": page})
            batch = parse_search_page(html)
            if not batch:
                break
            items.extend(batch)
            if len(batch) < page_size:
                break  # last page
            page += 1
            if self._config.geekhunter_delay_seconds:
                await asyncio.sleep(self._config.geekhunter_delay_seconds)
        return items[:limit]

    async def details(self, item: dict) -> dict:
        """Fetch the job page and merge it into `item` (partial-success)."""
        url = item.get("url")
        if not url:
            return item
        html = await self._get(url)
        try:
            detail = parse_job_detail(html)
        except KeyError:
            return item
        return merge_detail(item, detail)
