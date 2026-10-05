"""Kanban API — idempotent cards keyed on (source, source_id), status moves.

The suite shares one temp database (tests/conftest.py), so an autouse fixture
wipes `kanban_jobs` and `jobs` around every test: no card or job may leak into
the next test's counts.
"""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, inspect, select

from app.db import SessionLocal, engine, init_db
from app.main import app
from app.models import Job, KanbanJob


def _wipe() -> None:
    init_db()
    with SessionLocal() as db:
        db.execute(delete(KanbanJob))
        db.execute(delete(Job))
        db.commit()


@pytest.fixture(autouse=True)
def isolated_state():
    _wipe()
    yield
    _wipe()


def _cards() -> int:
    with SessionLocal() as db:
        return db.scalar(select(func.count()).select_from(KanbanJob)) or 0


def _seed_job(source: str = "gupy", source_id: str = "42", **overrides) -> None:
    fields = {
        "title": "SRE Pleno",
        "company": "ACME",
        "location": "Brazil",
        "url": "https://example.test/j/42",
        "remote": True,
    }
    fields.update(overrides)
    with SessionLocal() as db:
        db.add(Job(source=source, source_id=source_id, **fields))
        db.commit()


def test_kanban_table_created_with_unique_constraint():
    inspector = inspect(engine)
    assert "kanban_jobs" in inspector.get_table_names()
    unique = inspector.get_unique_constraints("kanban_jobs")
    assert any(
        constraint["name"] == "uq_kanban_jobs_source_source_id"
        and constraint["column_names"] == ["source", "source_id"]
        for constraint in unique
    ), unique


def test_kanban_create_starts_in_check_with_job_snapshot():
    _seed_job()
    with TestClient(app) as client:
        response = client.post("/kanban", json={"source": "gupy", "source_id": "42"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CHECK"
    assert body["title"] == "SRE Pleno"
    assert body["company"] == "ACME"
    assert body["remote"] is True
    assert body["url"] == "https://example.test/j/42"
    assert body["applied_at"] is None


def test_kanban_create_without_job_in_jobs_is_allowed():
    """The origin only needs to be identifiable — never required to exist."""
    with TestClient(app) as client:
        response = client.post("/kanban", json={"source": "linkedin", "source_id": "ghost"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "CHECK"
    assert body["title"] is None
    assert body["url"] is None
    assert body["applied_at"] is None


def test_kanban_create_requires_source_and_source_id():
    with TestClient(app) as client:
        missing_source_id = client.post("/kanban", json={"source": "gupy"})
        empty_body = client.post("/kanban", json={})
    assert missing_source_id.status_code == 422
    assert empty_body.status_code == 422


def test_kanban_create_is_idempotent():
    payload = {"source": "gupy", "source_id": "42"}
    with TestClient(app) as client:
        first = client.post("/kanban", json=payload)
        second = client.post("/kanban", json=payload)
    assert first.status_code == second.status_code == 200
    assert first.headers["X-Already-Existed"] == "false"
    assert second.headers["X-Already-Existed"] == "true"
    assert second.json()["id"] == first.json()["id"]
    assert _cards() == 1


def test_kanban_create_recovers_from_duplicate_insert(monkeypatch):
    """Race: the SELECT misses the row the other tab just committed (CA3)."""
    payload = {"source": "gupy", "source_id": "race"}
    with TestClient(app) as client:
        first = client.post("/kanban", json=payload)

    # Simula a corrida sem threads: o lookup inicial não enxerga a linha já
    # commitada, o INSERT bate na constraint e o recovery devolve a existente.
    from app.services import kanban as kanban_service

    real_find = kanban_service.find_kanban
    armed = {"value": True}

    def racy_find(db, source, source_id):
        if armed["value"]:
            armed["value"] = False  # stale read, como se a outra aba não commitasse
            return None
        return real_find(db, source, source_id)

    monkeypatch.setattr(kanban_service, "find_kanban", racy_find)

    with TestClient(app) as client:
        response = client.post("/kanban", json=payload)

    assert response.status_code == 200  # nunca 500
    assert response.json()["id"] == first.json()["id"]
    assert response.headers["X-Already-Existed"] == "true"
    assert _cards() == 1


def test_kanban_list_filters_by_status():
    with TestClient(app) as client:
        a = client.post("/kanban", json={"source": "gupy", "source_id": "a"}).json()
        b = client.post("/kanban", json={"source": "gupy", "source_id": "b"}).json()
        client.patch(f"/kanban/{b['id']}", json={"status": "DONE"})

        everything = client.get("/kanban")
        only_done = client.get("/kanban", params={"status": "DONE"})
        only_check = client.get("/kanban", params={"status": "CHECK"})
        invalid = client.get("/kanban", params={"status": "PAUSED"})

    assert everything.status_code == 200
    assert everything.json()["total"] == 2
    assert {item["id"] for item in everything.json()["items"]} == {a["id"], b["id"]}
    assert [item["status"] for item in only_done.json()["items"]] == ["DONE"]
    assert [item["id"] for item in only_check.json()["items"]] == [a["id"]]
    assert invalid.status_code == 422


def test_kanban_patch_moves_status():
    with TestClient(app) as client:
        created = client.post("/kanban", json={"source": "gupy", "source_id": "42"}).json()
        moved = client.patch(f"/kanban/{created['id']}", json={"status": "RUNNING"})
    assert moved.status_code == 200
    assert moved.json()["status"] == "RUNNING"
    assert moved.json()["applied_at"] is None  # só DONE carimba


def test_kanban_patch_rejects_unknown_status():
    with TestClient(app) as client:
        created = client.post("/kanban", json={"source": "gupy", "source_id": "42"}).json()
        response = client.patch(f"/kanban/{created['id']}", json={"status": "PAUSED"})
    assert response.status_code == 422


def test_kanban_patch_missing_id_is_404():
    with TestClient(app) as client:
        response = client.patch("/kanban/999999", json={"status": "DONE"})
    assert response.status_code == 404


def test_kanban_patch_done_stamps_applied_at():
    with TestClient(app) as client:
        created = client.post("/kanban", json={"source": "gupy", "source_id": "42"}).json()
        assert created["applied_at"] is None
        done = client.patch(f"/kanban/{created['id']}", json={"status": "DONE"})
    assert done.status_code == 200
    assert done.json()["status"] == "DONE"
    assert done.json()["applied_at"] is not None


def test_kanban_delete_removes_card():
    with TestClient(app) as client:
        created = client.post("/kanban", json={"source": "gupy", "source_id": "42"}).json()
        removed = client.delete(f"/kanban/{created['id']}")
        after = client.get("/kanban")
        again = client.delete(f"/kanban/{created['id']}")
    assert removed.status_code == 200
    assert removed.json() == {"deleted": created["id"]}
    assert after.json() == {"total": 0, "items": []}
    assert again.status_code == 404
    assert _cards() == 0


def test_jobs_excludes_kanban_jobs_in_items_and_total():
    """CA6: a vaga cardada some da lista; CA8: `total` leva o mesmo filtro."""
    _seed_job("gupy", "1", title="Keep me")
    _seed_job("gupy", "2", title="Carded")
    _seed_job("gupy", "3", title="Also keep")
    with TestClient(app) as client:
        client.post("/kanban", json={"source": "gupy", "source_id": "2"})
        everything = client.get("/jobs").json()
        paged = client.get("/jobs", params={"limit": 1}).json()
        filtered = client.get("/jobs", params={"source": "gupy"}).json()

    assert everything["total"] == 2
    assert {item["source_id"] for item in everything["items"]} == {"1", "3"}
    # paginação: count_stmt precisa receber o mesmo filtro que o stmt
    assert paged["total"] == 2
    assert len(paged["items"]) == 1
    assert filtered["total"] == 2


def test_kanban_card_survives_job_deletion_and_recollection():
    """CA7: snapshot fiel — o card não troca de vaga quando o rowid é reciclado."""
    _seed_job("gupy", "77", title="Original title", url="https://example.test/original")
    with TestClient(app) as client:
        card = client.post("/kanban", json={"source": "gupy", "source_id": "77"}).json()
        cleaned = client.delete("/jobs")
        # a linha de origem some de jobs (o clean dela poupou; aqui simula-se
        # um rowid reciclado): apagar tudo e recoletar a mesma identidade
        with SessionLocal() as db:
            db.execute(delete(Job))
            db.commit()
        _seed_job("gupy", "77", title="Recollected title", url="https://example.test/new")
        cards = client.get("/kanban").json()
        jobs = client.get("/jobs").json()

    # edge case: 0 removíveis e 1 no Kanban
    assert cleaned.json() == {"deleted": 0, "kept": 1}
    assert cards["total"] == 1
    item = cards["items"][0]
    assert item["id"] == card["id"]
    assert item["title"] == "Original title"
    assert item["company"] == "ACME"
    assert item["url"] == "https://example.test/original"
    # a recoleção da mesma identidade continua escondida atrás do mesmo card
    assert jobs["total"] == 0
