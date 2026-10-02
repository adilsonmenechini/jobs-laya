import json
from pathlib import Path
from typing import NamedTuple, Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classifier import build_classifier
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


def resolve_sources(source: str, registry: dict[str, JobSource] | None) -> list[JobSource]:
    """Map the request's `source` to concrete sources, failing loudly.

    An unavailable source raises instead of silently syncing another
    provider (same spirit as the example repo's `missing_config` error).
    """
    registry = registry if registry is not None else build_sources()
    wanted = list(registry) if source == "all" else [source]
    missing = [name for name in wanted if name not in registry]
    if missing:
        raise SourceUnavailableError(f"source unavailable: {', '.join(missing)}")
    return [registry[name] for name in wanted]


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
    source: str = "linkedin",
    sources: dict[str, JobSource] | None = None,
) -> SyncOutcome:
    profile = load_profile(profile_path)
    classifier = build_classifier(profile)
    active = resolve_sources(source, sources)
    count = 0
    errors: dict[str, str] = {}

    per_keyword = max(1, limit // len(keywords))
    for provider in active:
        try:
            for keyword in keywords:
                items = await provider.search(keyword, location, per_keyword)
                for normalized in items[:per_keyword]:
                    normalized = to_source_item(normalized, source=provider.name)
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
    return SyncOutcome(count=count, errors=errors)


def list_jobs(
    db: Session,
    match: str | None = None,
    remote: bool | None = None,
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
        stmt.order_by(Job.score.desc().nullslast(), Job.created_at.desc())
        .offset(offset)
        .limit(limit)
    )
    return db.scalars(stmt).all(), db.scalar(count_stmt) or 0
