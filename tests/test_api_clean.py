"""DELETE /jobs — wipe every persisted job, leave everything else alone."""

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Job


def _count() -> int:
    init_db()
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Job)) or 0


def _seed(n: int) -> None:
    init_db()
    with SessionLocal() as db:
        for i in range(n):
            db.add(Job(source="gupy", source_id=f"clean-{i}", title=f"Job {i}"))
        db.commit()


def test_delete_jobs_returns_count_and_empties_list():
    baseline = _count()
    _seed(2)
    with TestClient(app) as client:
        response = client.delete("/jobs")
        assert response.status_code == 200
        assert response.json() == {"deleted": baseline + 2}
        assert client.get("/jobs").json()["total"] == 0


def test_delete_jobs_on_empty_db_returns_zero():
    with TestClient(app) as client:
        client.delete("/jobs")
        response = client.delete("/jobs")
    assert response.status_code == 200
    assert response.json() == {"deleted": 0}


def test_delete_jobs_keeps_profile_and_schema():
    with TestClient(app) as client:
        before = client.get("/profile")
        client.delete("/jobs")
        after = client.get("/profile")
        # schema survives: health + jobs endpoint still answer
        assert client.get("/health").status_code == 200
        assert client.get("/jobs").status_code == 200
    assert before.status_code == after.status_code == 200
    assert before.json() == after.json()
