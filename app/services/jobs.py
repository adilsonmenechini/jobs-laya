import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classifier import build_classifier
from app.config import settings
from app.models import Job
from app.sources import JobSource, SourceUnavailableError, build_sources

JOB_COLUMNS = {c.name for c in Job.__table__.columns}


class Classifier(Protocol):
    def classify(self, job: dict) -> dict: ...


def load_profile(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def to_source_item(normalized: dict, source: str | None = None) -> dict:
    """Map a provider payload into the Job `(source, source_id)` contract.

    LinkedIn parsing still emits `linkedin_id`; this is the single choke
    point that turns it into the provider-agnostic shape `upsert_job` stores.
    Idempotent: `merge_job_details` may re-add `linkedin_id` after a call.
    """
    item = dict(normalized)
    if "linkedin_id" in item:
        item["source_id"] = item.pop("linkedin_id") or item.get("source_id", "")
    item.setdefault("source_id", "")
    if source is not None:
        item["source"] = source
    else:
        item.setdefault("source", "linkedin")
    return item


def upsert_job(db: Session, normalized: dict, classifier: Classifier) -> Job:
    normalized = to_source_item(normalized)
    # Sources may carry extras (`skills`, `company_slug`, …): persist only
    # model columns, but let the classifier see the full normalized item.
    payload = {k: v for k, v in normalized.items() if k in JOB_COLUMNS}
    existing = db.scalar(
        select(Job).where(
            Job.source == normalized["source"],
            Job.source_id == normalized["source_id"],
        )
    )
    result = classifier.classify(normalized)
    if existing is None:
        existing = Job(**payload)
        db.add(existing)

    for key, value in payload.items():
        setattr(existing, key, value)
    existing.match = result["match"]
    existing.score = result["score"]
    existing.decision = result["decision"]
    existing.reasons = result["reasons"]
    existing.gaps = result["gaps"]
    db.commit()
    db.refresh(existing)
    return existing


def resolve_sources(source: str, registry: dict[str, JobSource]) -> list[JobSource]:
    """Map the request's `source` to concrete sources, failing loudly.

    An unavailable source raises instead of silently syncing another
    provider (same spirit as the example repo's `missing_config` error).
    Building the registry is the caller's job — the builder also closes it
    (see `sync_jobs`), so nothing is constructed here to be dropped unclosed.
    """
    wanted = list(registry) if source == "all" else [source]
    missing = [name for name in wanted if name not in registry]
    if missing:
        raise SourceUnavailableError(f"source unavailable: {', '.join(missing)}")
    return [registry[name] for name in wanted]


def is_fresh(posted_at: str | None, hours_old: int, now: datetime | None = None) -> bool:
    """True when the posting is inside the recency window — or undatable.

    `hours_old <= 0` disables the window. Missing (`None`/blank) and
    unparseable dates are KEPT: sources emit relative text
    ("Publicada há 5 dias") and dropping a job we cannot date is worse than
    keeping a stale one. `posted_at` is day-granular, so the boundary lands
    anywhere inside the last day of the window (lenient by design).
    """
    if hours_old <= 0 or not posted_at:
        return True
    try:
        posted = datetime.strptime(posted_at[:10], "%Y-%m-%d").date()
    except ValueError:
        return True
    reference = now or datetime.now()
    return posted >= (reference - timedelta(hours=hours_old)).date()


class SyncOutcome(NamedTuple):
    """Result of a sync run: how many jobs landed and what failed upstream."""

    count: int
    errors: dict[str, str]


async def sync_jobs(
    db: Session,
    keywords: list[str],
    location: str,
    limit: int,
    fetch_details: bool,
    profile_path: str,
    source: str = "all",
    sources: dict[str, JobSource] | None = None,
    hours_old: int | None = None,
    delay_seconds: float | None = None,
    sync_timeout_seconds: float | None = None,
) -> SyncOutcome:
    profile = load_profile(profile_path)
    classifier = build_classifier(profile)
    # Ownership: a registry built here gets closed here (finally below). An
    # injected one stays open — whoever passed it decides its lifecycle
    # (test fakes, callers reusing a shared registry).
    registry = sources if sources is not None else build_sources()
    try:
        active = resolve_sources(source, registry)
        window = settings.hours_old if hours_old is None else hours_old
        pause = settings.sync_delay_seconds if delay_seconds is None else delay_seconds
        timeout = (
            settings.sync_timeout_seconds if sync_timeout_seconds is None else sync_timeout_seconds
        )
        count = 0
        errors: dict[str, str] = {}

        per_keyword = max(1, limit // len(keywords))

        async def _run_sync() -> SyncOutcome:
            nonlocal count
            for index, provider in enumerate(active):
                if index and pause:
                    # Politeness between providers: a burst of back-to-back sources
                    # from one IP is what gets throttled (JobSpy-style site spacing).
                    await asyncio.sleep(pause)
                try:
                    for keyword in keywords:
                        items = await provider.search(keyword, location, per_keyword)
                        for normalized in items[:per_keyword]:
                            normalized = to_source_item(normalized, source=provider.name)
                            if not is_fresh(normalized.get("posted_at"), window):
                                continue  # outside the recency window — skip early
                            if fetch_details:
                                try:
                                    normalized = await provider.details(normalized)
                                except Exception:
                                    # Partial-success: keep the search payload when
                                    # the detail fetch fails (any reason).
                                    pass
                            upsert_job(db, normalized, classifier)
                            count += 1
                except SourceUnavailableError as exc:
                    # One dead source must not erase what the others delivered:
                    # results stay persisted and the failure is reported per source.
                    errors[provider.name] = str(exc)
                except Exception as exc:
                    # Any other failure (parsing, DB, classifier) must also degrade
                    # only this source. CancelledError is BaseException, so deadline
                    # cancellation still propagates.
                    errors[provider.name] = f"unexpected error: {exc}"
            return SyncOutcome(count=count, errors=errors)

        if timeout and timeout > 0:
            async with asyncio.timeout(timeout):
                return await _run_sync()
        return await _run_sync()
    finally:
        if sources is None:
            # The registry was rebuilt for this run: closing it releases the
            # per-source httpx pools. Covers success, resolve failure (503)
            # and any exception — the leak was "built and never closed".
            for provider in registry.values():
                try:
                    await provider.aclose()
                except Exception:  # noqa: BLE001
                    pass  # shutdown must never mask the sync outcome


def list_jobs(
    db: Session,
    match: str | None = None,
    remote: bool | None = None,
    location: str | None = None,
    query: str | None = None,
    min_score: float | None = None,
    source: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    stmt = select(Job)
    count_stmt = select(func.count()).select_from(Job)

    filters = []
    if match:
        filters.append(Job.match == match)
    if remote is not None:
        filters.append(Job.remote == remote)
    if location:
        loc = f"%{location.lower()}%"
        filters.append(Job.location.ilike(loc))
    if min_score is not None:
        filters.append(Job.score >= min_score)
    if source:
        filters.append(Job.source == source)
    if query:
        q = f"%{query.lower()}%"
        filters.append((Job.title.ilike(q)) | (Job.company.ilike(q)) | (Job.description.ilike(q)))

    for condition in filters:
        stmt = stmt.where(condition)
        count_stmt = count_stmt.where(condition)

    stmt = (
        stmt.order_by(Job.created_at.desc().nullslast(), Job.score.desc().nullslast())
        .offset(offset)
        .limit(limit)
    )
    return db.scalars(stmt).all(), db.scalar(count_stmt) or 0
