"""Fase 4 — sync dispatcher: per-source execution and fault isolation."""

from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Job
from app.services.jobs import is_fresh, resolve_sources, sync_jobs
from app.sources import SourceUnavailableError

PROFILE = "data/profile.json"


@pytest.fixture(autouse=True)
def fake_classifier_backend(monkeypatch):
    """Sync tests must never load the real Laya checkpoint (README: suite
    runs with FakeEngine, no model download)."""
    from app.config import settings

    monkeypatch.setattr(settings, "classifier_backend", "fake")


@pytest.fixture(autouse=True)
def no_inter_source_pause(monkeypatch):
    """The default politeness pause between sources would put real seconds
    into every test; tests that exercise the pause pass it explicitly."""
    from app.config import settings

    monkeypatch.setattr(settings, "sync_delay_seconds", 0.0)


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


def run(db, source: str, sources: dict, **kwargs):
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
            **kwargs,
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


def test_sync_all_isolates_expired_linkedin_session(db):
    """An expired LinkedIn session (ToolError) must degrade only that source:
    the GeekHunter half of `all` still runs, and the login hint is reported."""
    from app.linkedin.errors import ToolError
    from app.sources.linkedin import LinkedInSource

    class ExpiredClient:
        async def search_jobs(self, *args, **kwargs):
            raise ToolError("LinkedIn session not found — run `make login` first")

    linkedin = LinkedInSource(client=ExpiredClient())
    geekhunter = FakeSource("geekhunter", [gh_item("2")])

    outcome = run(db, "all", {"linkedin": linkedin, "geekhunter": geekhunter})

    assert outcome.count == 1  # geekhunter delivered
    assert "make login" in outcome.errors["linkedin"]
    assert [job.source for job in db.scalars(select(Job)).all()] == ["geekhunter"]


def test_sync_unknown_source_fails_loudly(db):
    with pytest.raises(SourceUnavailableError):
        run(db, "geekhunter", {"linkedin": FakeSource("linkedin", [])})


# -------------------------------------------------------------------- recency


def test_is_fresh_keeps_recent_and_drops_stale_postings():
    now = datetime(2026, 10, 2, 12, 0)

    assert is_fresh("2026-10-01", 72, now=now)  # yesterday: inside the window
    assert is_fresh("2026-09-29", 72, now=now)  # boundary day: kept (day precision)
    assert not is_fresh("2026-09-28", 72, now=now)  # well past 72h: stale
    assert not is_fresh("2026-01-01", 72, now=now)


def test_is_fresh_keeps_undatable_postings():
    """Sources without a date, or with relative text, must never be dropped."""
    now = datetime(2026, 10, 2, 12, 0)

    assert is_fresh(None, 72, now=now)  # no date sent at all
    assert is_fresh("", 72, now=now)
    # GeekHunter falls back to relative PT strings — undatable, keep
    assert is_fresh("Publicada há 5 dias", 72, now=now)
    # ISO datetime (Gupy: "…T13:23:13.263Z") parses through its date prefix
    assert is_fresh("2026-10-01T13:23:13.263Z", 72, now=now)
    assert not is_fresh("2026-09-01T13:23:13.263Z", 72, now=now)


def test_is_fresh_window_zero_disables_the_filter():
    assert is_fresh("2020-01-01", 0)
    assert is_fresh("2020-01-01", -1)


def test_sync_skips_postings_older_than_the_window(db):
    stale = gh_item("stale")
    stale["posted_at"] = (date.today() - timedelta(days=10)).isoformat()
    fresh = gh_item("fresh")
    fresh["posted_at"] = date.today().isoformat()

    # window passed explicitly: the test must not shift with the default
    outcome = run(db, "all", {"gupy": FakeSource("gupy", [stale, fresh])}, hours_old=72)

    assert outcome.count == 1  # only the fresh posting landed
    assert [job.source_id for job in db.scalars(select(Job)).all()] == ["fresh"]


def test_sync_keeps_postings_without_a_date(db):
    # gh_item carries posted_at=None by default: undated jobs must not vanish
    outcome = run(db, "all", {"gupy": FakeSource("gupy", [gh_item("1")])})

    assert outcome.count == 1
    assert [job.source_id for job in db.scalars(select(Job)).all()] == ["1"]


def test_sync_hours_old_zero_keeps_stale_postings(db):
    stale = gh_item("stale")
    stale["posted_at"] = (date.today() - timedelta(days=30)).isoformat()

    outcome = run(db, "all", {"gupy": FakeSource("gupy", [stale])}, hours_old=0)

    assert outcome.count == 1  # window disabled → everything is kept


# ------------------------------------------------------- inter-source politeness


def test_sync_all_pauses_between_sources(db, monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.services.jobs.asyncio.sleep", fake_sleep)
    registry = {
        "linkedin": FakeSource("linkedin", [li_item("1")]),
        "geekhunter": FakeSource("geekhunter", [gh_item("2")]),
    }

    run(db, "all", registry, delay_seconds=1.5)

    assert slept == [1.5]  # one pause, between the two providers


def test_sync_single_source_never_pauses(db, monkeypatch):
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.services.jobs.asyncio.sleep", fake_sleep)

    run(
        db,
        "geekhunter",
        {"geekhunter": FakeSource("geekhunter", [gh_item("2")])},
        delay_seconds=1.5,
    )

    assert slept == []  # nothing to be polite to


def test_resolve_sources_all_returns_every_registry_entry():
    registry = {
        "linkedin": FakeSource("linkedin", []),
        "geekhunter": FakeSource("geekhunter", []),
    }
    resolved = resolve_sources("all", registry)
    assert [source.name for source in resolved] == ["linkedin", "geekhunter"]


def test_sync_endpoint_default_source_is_all(db):
    """No `source` in the body must run every configured source."""
    from app.services import jobs as jobs_service

    request: dict = {"keywords": ["SRE"], "limit": 5, "fetch_details": False}
    registry = {
        "geekhunter": FakeSource("geekhunter", []),
        "gupy": FakeSource("gupy", []),
    }
    original = jobs_service.build_sources
    jobs_service.build_sources = lambda config=None: registry
    try:
        # exercising the default only: fakes replace the real providers, so the
        # browser never launches and nothing hits the network.
        with TestClient(app) as client:
            response = client.post("/jobs/sync", json=request)
    finally:
        jobs_service.build_sources = original

    assert response.status_code == 200
    # "all" resolved both registered sources (linkedin alone would be 0 searches)
    assert all(len(source.searches) > 0 for source in registry.values())


def test_sync_endpoint_rejects_unknown_source(db):
    with TestClient(app) as client:
        response = client.post("/jobs/sync", json={"keywords": ["SRE"], "source": "brave"})
    assert response.status_code == 422


def test_sync_endpoint_rejects_negative_hours_old(db):
    with TestClient(app) as client:
        response = client.post("/jobs/sync", json={"keywords": ["SRE"], "hours_old": -1})
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
