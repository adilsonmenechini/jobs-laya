"""TDD: per-source fault isolation for generic exceptions."""

import asyncio

import pytest
from sqlalchemy import select

from app.db import SessionLocal, init_db
from app.models import Job
from app.services.jobs import sync_jobs
from app.sources import SourceUnavailableError

PROFILE = "data/profile.json"


@pytest.fixture(autouse=True)
def fake_classifier_backend(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "classifier_backend", "fake")


@pytest.fixture(autouse=True)
def no_inter_source_pause(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "sync_delay_seconds", 0.0)


class FakeSource:
    """Scripted JobSource: fixed items, optional failure, records calls."""

    def __init__(self, name: str, items: list[dict], fail: Exception | None = None):
        self.name = name
        self.items = items
        self.fail = fail
        self.searches: list[tuple[str, str, int]] = []

    async def search(self, keywords: str, location: str, limit: int = 25) -> list[dict]:
        self.searches.append((keywords, location, limit))
        if self.fail:
            raise self.fail
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


def test_sync_all_isolates_generic_exception_per_source(db):
    """RuntimeError in the middle source must not abort the loop."""
    source_a = FakeSource("source_a", [li_item("1")])
    source_b = FakeSource("source_b", [gh_item("2")], fail=RuntimeError("parsing blew up"))
    source_c = FakeSource("source_c", [gh_item("3")])

    outcome = run(db, "all", {"source_a": source_a, "source_b": source_b, "source_c": source_c})

    assert outcome.count == 2  # source_a + source_c delivered
    assert "source_b" in outcome.errors
    assert "parsing blew up" in outcome.errors["source_b"]
    # sources before and after both ran
    assert source_a.searches == [("SRE", "Brazil", 10)]
    assert source_b.searches == [("SRE", "Brazil", 10)]  # started but raised
    assert source_c.searches == [("SRE", "Brazil", 10)]
    # persisted jobs: source_a (linkedin) + source_c (geekhunter)
    jobs = db.scalars(select(Job)).all()
    # to_source_item() overwrites source with provider.name
    sources_present = {job.source for job in jobs}
    assert sources_present == {"source_a", "source_c"}
    source_ids = {job.source_id for job in jobs}
    assert source_ids == {"1", "3"}


def test_sync_generic_exception_message_distinguishable(db):
    """Generic exception message must be distinguishable from SourceUnavailableError."""
    source_a = FakeSource("source_a", [li_item("1")])
    source_b = FakeSource("source_b", [gh_item("2")], fail=RuntimeError("unexpected boom"))

    outcome = run(db, "all", {"source_a": source_a, "source_b": source_b})

    assert "source_b" in outcome.errors
    msg = outcome.errors["source_b"]
    # The SPEC requires a prefix to distinguish from SourceUnavailableError
    assert msg.startswith("unexpected error:") or "unexpected" in msg.lower()


def test_sync_cancelled_error_propagates(db):
    """asyncio.CancelledError must NOT be caught by the generic handler."""
    source_a = FakeSource("source_a", [li_item("1")])
    source_b = FakeSource("source_b", [gh_item("2")], fail=asyncio.CancelledError())
    source_c = FakeSource("source_c", [gh_item("3")])

    with pytest.raises(asyncio.CancelledError):
        run(db, "all", {"source_a": source_a, "source_b": source_b, "source_c": source_c})
    # If we get here without exception, the test failed (cancelled was swallowed)


def test_sync_source_unavailable_error_unchanged(db):
    """Regression: SourceUnavailableError keeps its exact current message."""
    source_a = FakeSource("source_a", [li_item("1")])
    source_b = FakeSource("source_b", [], fail=SourceUnavailableError("make login first"))

    outcome = run(db, "all", {"source_a": source_a, "source_b": source_b})

    assert "source_b" in outcome.errors
    assert outcome.errors["source_b"] == "make login first"  # exact text preserved
