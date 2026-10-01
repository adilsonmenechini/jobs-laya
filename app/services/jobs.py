import json
from pathlib import Path
from typing import Protocol

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.classifier import build_classifier
from app.linkedin.local_client import LinkedInBrowserClient
from app.linkedin.parsing import extract_job_items, merge_job_details
from app.models import Job


class Classifier(Protocol):
    def classify(self, job: dict) -> dict: ...


def load_profile(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def upsert_job(db: Session, normalized: dict, classifier: Classifier) -> Job:
    existing = db.scalar(select(Job).where(Job.linkedin_id == normalized["linkedin_id"]))
    result = classifier.classify(normalized)
    if existing is None:
        existing = Job(**normalized)
        db.add(existing)

    for key, value in normalized.items():
        setattr(existing, key, value)
    existing.match = result["match"]
    existing.score = result["score"]
    existing.decision = result["decision"]
    existing.reasons = result["reasons"]
    existing.gaps = result["gaps"]
    db.commit()
    db.refresh(existing)
    return existing


async def sync_jobs(
    db: Session,
    keywords: list[str],
    location: str,
    limit: int,
    fetch_details: bool,
    profile_path: str,
) -> int:
    profile = load_profile(profile_path)
    classifier = build_classifier(profile)
    client = LinkedInBrowserClient()
    count = 0

    per_keyword = max(1, limit // len(keywords))
    for keyword in keywords:
        result = await client.search_jobs(keyword, location, per_keyword)
        items = extract_job_items(result)[:per_keyword]

        for normalized in items:
            if fetch_details:
                try:
                    details = await client.get_job_details(normalized["linkedin_id"])
                    # A failed detail parse must never wipe the search payload.
                    merge_job_details(normalized, details)
                except Exception:
                    # Keep search result when details fail; sync should be partial-success.
                    pass
            upsert_job(db, normalized, classifier)
            count += 1
    return count


def list_jobs(
    db: Session,
    match: str | None = None,
    remote: bool | None = None,
    query: str | None = None,
    min_score: float | None = None,
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
