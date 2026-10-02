"""Fase 2 — multi-source Job model: dedup key, schema, and list filter."""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Job
from app.schemas import JobSearchRequest
from app.services.jobs import list_jobs, upsert_job


class FakeClassifier:
    def classify(self, job: dict) -> dict:
        return {
            "match": "high",
            "score": 90.0,
            "decision": {"source": job.get("source")},
            "reasons": ["ok"],
            "gaps": [],
        }


def make_item(source: str, source_id: str, **extra) -> dict:
    item = {
        "source": source,
        "source_id": source_id,
        "title": f"Job {source_id}",
        "company": "Acme",
        "location": "Brazil",
        "remote": True,
        "url": "https://example.com/job",
        "description": "desc",
        "posted_at": None,
        "raw": {"x": 1},
    }
    item.update(extra)
    return item


@pytest.fixture()
def db():
    init_db()
    session = SessionLocal()
    yield session
    session.rollback()
    for job in session.scalars(select(Job)).all():
        session.delete(job)
    session.commit()
    session.close()


def test_upsert_dedupes_per_source(db):
    classifier = FakeClassifier()

    first = upsert_job(db, make_item("linkedin", "123", title="First"), classifier)
    second = upsert_job(db, make_item("linkedin", "123", title="Second"), classifier)

    assert first.id == second.id
    assert second.title == "Second"
    assert db.scalar(select(Job).where(Job.source == "linkedin")) is not None
    assert len(db.scalars(select(Job)).all()) == 1


def test_same_id_in_different_sources_are_different_jobs(db):
    classifier = FakeClassifier()

    upsert_job(db, make_item("linkedin", "123"), classifier)
    upsert_job(db, make_item("geekhunter", "123"), classifier)

    jobs = db.scalars(select(Job)).all()
    assert len(jobs) == 2
    assert {job.source for job in jobs} == {"linkedin", "geekhunter"}


def test_upsert_classifies_every_time(db):
    classifier = FakeClassifier()

    job = upsert_job(db, make_item("geekhunter", "1"), classifier)
    assert job.match == "high"
    assert job.score == 90.0
    assert job.decision == {"source": "geekhunter"}


def test_list_jobs_filters_by_source(db):
    classifier = FakeClassifier()
    upsert_job(db, make_item("linkedin", "1", title="LinkedIn job"), classifier)
    upsert_job(db, make_item("geekhunter", "2", title="GeekHunter job"), classifier)

    only_geek, total = list_jobs(db, source="geekhunter")
    everything, total_all = list_jobs(db)

    assert total == 1
    assert [job.source for job in only_geek] == ["geekhunter"]
    assert total_all == 2


def test_list_jobs_orders_newest_first_then_by_score(db):
    """Front order: newest created → oldest; ties broken by higher score."""
    classifier = FakeClassifier()
    older = upsert_job(db, make_item("gupy", "old"), classifier)
    new_low = upsert_job(db, make_item("gupy", "new-low"), classifier)
    new_high = upsert_job(db, make_item("gupy", "new-high"), classifier)

    # pin timestamps and scores: insert order alone would tie and hide the rule
    older.created_at = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)
    new_low.created_at = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    new_high.created_at = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)
    older.score = 99.0
    new_low.score = 10.0
    new_high.score = 90.0
    db.commit()

    jobs, total = list_jobs(db)

    assert total == 3
    # newest moment first, higher score inside that moment, oldest last
    assert [job.source_id for job in jobs] == ["new-high", "new-low", "old"]


def test_job_search_request_source_defaults_to_all():
    request = JobSearchRequest(keywords=["SRE"])
    assert request.source == "all"


def test_job_search_request_accepts_all_sources():
    for source in ("linkedin", "geekhunter", "gupy", "indeed", "glassdoor", "all"):
        assert JobSearchRequest(keywords=["SRE"], source=source).source == source


def test_job_search_request_rejects_unknown_source():
    with pytest.raises(ValueError):
        JobSearchRequest(keywords=["SRE"], source="brave")


def test_job_search_request_hours_old_defaults_to_30_days():
    assert JobSearchRequest(keywords=["SRE"]).hours_old == 720


def test_job_search_request_hours_old_accepts_the_presets():
    # front presets: 1d · 72h · 7d · 30d · sem filtro
    for value in (0, 24, 72, 168, 720):
        assert JobSearchRequest(keywords=["SRE"], hours_old=value).hours_old == value


def test_job_search_request_hours_old_rejects_negative():
    with pytest.raises(ValueError):
        JobSearchRequest(keywords=["SRE"], hours_old=-1)


def test_job_out_exposes_source(db):
    classifier = FakeClassifier()
    job = upsert_job(db, make_item("geekhunter", "7"), classifier)

    with TestClient(app) as client:
        response = client.get("/jobs")

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "geekhunter"
    assert body["items"][0]["source_id"] == "7"
    assert body["items"][0]["id"] == job.id


def test_job_out_exposes_posted_at(db):
    """The recency window is invisible if the API hides the posting date."""
    classifier = FakeClassifier()
    upsert_job(db, make_item("indeed", "8", posted_at="2026-10-01"), classifier)
    upsert_job(db, make_item("gupy", "9", posted_at=None), classifier)

    with TestClient(app) as client:
        response = client.get("/jobs")

    by_source = {item["source"]: item for item in response.json()["items"]}
    assert by_source["indeed"]["posted_at"] == "2026-10-01"
    assert by_source["gupy"]["posted_at"] is None  # undated jobs still listed


def test_jobs_endpoint_filters_by_source(db):
    classifier = FakeClassifier()
    upsert_job(db, make_item("linkedin", "1"), classifier)
    upsert_job(db, make_item("geekhunter", "2"), classifier)

    with TestClient(app) as client:
        response = client.get("/jobs", params={"source": "geekhunter"})

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["source"] == "geekhunter"


def test_jobs_endpoint_rejects_unknown_source():
    with TestClient(app) as client:
        response = client.get("/jobs", params={"source": "brave"})

    assert response.status_code == 422


def test_jobs_endpoint_accepts_the_new_sources():
    """The `source` path regex must validate gupy, indeed and glassdoor (spec FR-3)."""
    with TestClient(app) as client:
        for source in ("gupy", "indeed", "glassdoor"):
            response = client.get("/jobs", params={"source": source})
            assert response.status_code == 200, source
            assert response.json()["total"] == 0
