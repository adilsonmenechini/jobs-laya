"""Normalization of LinkedIn MCP payloads into a stable local shape.

Shared by the sync service and the local tools layer so both interpret the
upstream (untrusted) payloads exactly the same way.
"""

from typing import Any


def normalize_job(item: dict) -> dict:
    """Normalize common LinkedIn MCP shapes without coupling API to scraper output."""
    data = item.get("job", item) if isinstance(item, dict) else {}
    job_id = str(data.get("job_id") or data.get("id") or data.get("entity_urn", "").split(":")[-1])
    return {
        "linkedin_id": job_id,
        "title": data.get("title") or data.get("job_title") or "Unknown",
        "company": data.get("company") or data.get("company_name"),
        "location": data.get("location"),
        "remote": bool(data.get("remote") or data.get("workplace_type") in {"REMOTE", "Remote"}),
        "url": data.get("url") or data.get("job_url"),
        "description": data.get("description") or "",
        "posted_at": data.get("posted_at") or data.get("listed_at"),
        "raw": data,
    }


EMPTY_VALUES = (None, "", "Unknown")


def merge_job_details(search: dict, details: dict | None) -> dict:
    """Merge a detail payload into a search item without destroying good data.

    A failed detail parse (empty or title-less payload) must never wipe the
    title/company/id the search already found; `remote` only ever upgrades
    to True, since a broken top card cannot prove a job is on-site.
    """
    if not details:
        return search
    detail = normalize_job(details)
    if detail["title"] in EMPTY_VALUES and not detail["description"]:
        return search
    for key, value in detail.items():
        if key == "remote":
            if value:
                search[key] = True
        elif value not in EMPTY_VALUES:
            search[key] = value
    return search


def extract_job_items(result: Any) -> list[dict]:
    """Extract normalized job items from any upstream search/detail payload shape."""
    if isinstance(result, list):
        raw_items = result
    elif isinstance(result, dict):
        if any(key in result for key in ("title", "job_title", "job_id", "job")):
            raw_items = [result]
        else:
            raw_items = result.get("jobs") or result.get("results") or result.get("items") or []
    else:
        raw_items = []

    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        normalized = normalize_job(raw)
        if normalized["linkedin_id"]:
            items.append(normalized)
    return items
