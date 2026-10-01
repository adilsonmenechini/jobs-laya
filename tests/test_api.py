from fastapi.testclient import TestClient

from app.main import app


def test_health():
    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


def test_profile():
    with TestClient(app) as client:
        response = client.get("/profile")
        assert response.status_code == 200
        assert "skills" in response.json()


def test_jobs_empty_list():
    with TestClient(app) as client:
        response = client.get("/jobs")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == len(body["items"]) == 0


def test_job_not_found():
    with TestClient(app) as client:
        response = client.get("/jobs/999999")
        assert response.status_code == 404
