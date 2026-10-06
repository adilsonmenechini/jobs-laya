"""DELETE /jobs — wipe collected jobs outside the Kanban, leave the rest alone."""

from fastapi.testclient import TestClient
from sqlalchemy import delete, exists, func, select

from app.db import SessionLocal, init_db
from app.main import app
from app.models import Job, KanbanJob


def _count() -> int:
    init_db()
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(Job)) or 0


def _cards() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(KanbanJob)) or 0


def _shielded() -> int:
    """Linhas de `jobs` com card no Kanban — o clean precisa poupá-las."""
    with SessionLocal() as db:
        return (
            db.scalar(
                select(func.count())
                .select_from(Job)
                .where(
                    exists().where(
                        KanbanJob.source == Job.source,
                        KanbanJob.source_id == Job.source_id,
                    )
                )
            )
            or 0
        )


def _seed(n: int) -> None:
    init_db()
    with SessionLocal() as db:
        for i in range(n):
            db.add(Job(source="gupy", source_id=f"clean-{i}", title=f"Job {i}"))
        db.commit()


def test_delete_jobs_returns_count_and_empties_list():
    baseline = _count()
    shielded = _shielded()
    kept_cards = _cards()
    _seed(2)
    with TestClient(app) as client:
        response = client.delete("/jobs")
        assert response.status_code == 200
        assert response.json() == {"deleted": baseline + 2 - shielded, "kept": kept_cards}
        assert client.get("/jobs").json()["total"] == 0


def test_delete_jobs_on_empty_db_returns_zero():
    kept_cards = _cards()
    with TestClient(app) as client:
        client.delete("/jobs")
        response = client.delete("/jobs")
    assert response.status_code == 200
    assert response.json() == {"deleted": 0, "kept": kept_cards}


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


def test_clean_keeps_kanban_rows_and_reports_kept():
    """CA5: o clean apaga só vagas fora do Kanban e reporta as preservadas."""
    init_db()
    with SessionLocal() as db:
        db.execute(delete(KanbanJob))
        db.execute(delete(Job))
        db.commit()
    _seed(2)
    with SessionLocal() as db:
        db.add(KanbanJob(source="gupy", source_id="clean-1", title="Job 1", status="RUNNING"))
        db.commit()

    with TestClient(app) as client:
        response = client.delete("/jobs")
        cards = client.get("/kanban").json()

    assert response.status_code == 200
    assert response.json() == {"deleted": 1, "kept": 1}
    # a linha protegida segue no banco — some apenas da listagem
    assert _count() == 1
    assert cards["total"] == 1
    assert cards["items"][0]["source_id"] == "clean-1"
    assert cards["items"][0]["title"] == "Job 1"
