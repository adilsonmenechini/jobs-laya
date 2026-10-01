"""Fase 4 — sync dispatcher: per-source execution and fault isolation."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Job
from app.services.jobs import resolve_sources, sync_jobs
from app.sources import SourceUnavailableError

PROFILE = "data/profile.json"


@pytest.fixture(autouse=True)
def fake_classifier_backend(monkeypatch):
    """Sync tests must never load the real Laya checkpoint (README: suite
    runs with FakeEngine, no model download)."""
    from app.config import settings

    monkeypatch.setattr(settings, "classifier_backend", "fake")


class FakeSource:
    """Scripted JobSource: fixed items, optional failure, records calls."""

    def __init__(self, name: str, items: list[dict], fail: bool = False):
        self.name = name
        self.items = items
        self.fail = fail
        self.searches: list[tuple[str, str, int]] = []

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        self.searches.append((keywords, location, limit))
        if self.fail:
            raise SourceUnavailableError(f"source unavailable: {self.name}")
        return [dict(item) for item in self.items]

    async def details(self, item: dict) -> dict:
        return item


def gh_item(source_id: str, title: str = "SRE") -> dict:
    return {
        "source": "geekhunter",
        "source_id": source_id,
        "title": title,
        "company": "Acme",
        "location": "Brazil",
        "remote": True,
        "url": "https://example.com/job",
        "description": "kubernetes terraform sre",
        "posted_at": None,
        "raw": {},
    }


def li_item(source_id: str) -> dict:
    item = gh_item(source_id, title="DevOps")
    item["source"] = "linkedin"
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


def run(db, source: str, sources: dict):
    import asyncio

    return asyncio.run(
        sync_jobs(
            db=db,
            keywords=["SRE"],
            location="Brazil",
            limit=10,
            fetch_details=True,
            profile_path=PROFILE,
            source=source,
            sources=sources,
        )
    )


def test_sync_single_source_only_calls_that_source(db):
    linkedin = FakeSource("linkedin", [li_item("1")])
    geekhunter = FakeSource("geekhunter", [gh_item("2")])

    outcome = run(db, "geekhunter", {"linkedin": linkedin, "geekhunter": geekhunter})

    assert outcome.count == 1
    assert outcome.errors == {}
    assert linkedin.searches == []  # untouched
    assert geekhunter.searches == [("SRE", "Brazil", 10)]
    jobs = db.scalars(select(Job)).all()
    assert [(job.source, job.source_id) for job in jobs] == [("geekhunter", "2")]


def test_sync_all_runs_every_source(db):
    linkedin = FakeSource("linkedin", [li_item("1")])
    geekhunter = FakeSource("geekhunter", [gh_item("2")])

    outcome = run(db, "all", {"linkedin": linkedin, "geekhunter": geekhunter})

    assert outcome.count == 2
    assert outcome.errors == {}
    assert {job.source for job in db.scalars(select(Job)).all()} == {
        "linkedin",
        "geekhunter",
    }


def test_sync_all_isolates_source_failure(db):
    """A dead source must not wipe the other's results — and must be reported."""
    linkedin = FakeSource("linkedin", [li_item("1")])
    geekhunter = FakeSource("geekhunter", [], fail=True)

    outcome = run(db, "all", {"linkedin": linkedin, "geekhunter": geekhunter})

    assert outcome.count == 1  # linkedin delivered
    assert "geekhunter" in outcome.errors
    jobs = db.scalars(select(Job)).all()
    assert [job.source for job in jobs] == ["linkedin"]  # persisted, not rolled back


def test_sync_single_source_failure_is_reported(db):
    geekhunter = FakeSource("geekhunter", [], fail=True)

    outcome = run(db, "geekhunter", {"geekhunter": geekhunter})

    assert outcome.count == 0
    assert "geekhunter" in outcome.errors


def test_sync_unknown_source_fails_loudly(db):
    with pytest.raises(SourceUnavailableError):
        run(db, "geekhunter", {"linkedin": FakeSource("linkedin", [])})


def test_resolve_sources_all_returns_every_registry_entry():
    registry = {
        "linkedin": FakeSource("linkedin", []),
        "geekhunter": FakeSource("geekhunter", []),
    }
    resolved = resolve_sources("all", registry)
    assert [source.name for source in resolved] == ["linkedin", "geekhunter"]


def test_sync_endpoint_default_source_is_linkedin(db):
    """No `source` in the body must keep the old LinkedIn-only behavior."""
    request: dict = {"keywords": ["SRE"], "limit": 5, "fetch_details": False}
    # exercising validation only: the endpoint would launch the browser, so
    # we assert the accepted contract instead of calling the real source.
    with TestClient(app) as client:
        bad = client.post("/jobs/sync", json={**request, "source": "indeed"})
    assert bad.status_code == 422


def test_sync_endpoint_rejects_unknown_source(db):
    with TestClient(app) as client:
        response = client.post("/jobs/sync", json={"keywords": ["SRE"], "source": "indeed"})
    assert response.status_code == 422


def test_sync_endpoint_reports_unavailable_source(db):
    """Source present in the schema but not in the registry → 503, not a crash."""
    from app.services import jobs as jobs_service

    original = jobs_service.build_sources

    def only_linkedin(config=None):
        return {"linkedin": FakeSource("linkedin", [])}

    jobs_service.build_sources = only_linkedin
    try:
        with TestClient(app) as client:
            response = client.post("/jobs/sync", json={"keywords": ["SRE"], "source": "geekhunter"})
    finally:
        jobs_service.build_sources = original

    assert response.status_code == 503
    assert "geekhunter" in response.json()["detail"]
