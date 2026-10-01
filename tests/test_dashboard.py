"""Dashboard: static frontend served by FastAPI (pattern from the example repo)."""

from fastapi.testclient import TestClient

from app.main import app


def test_index_serves_dashboard():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "LinkedIn Job Classifier" in response.text
    assert 'id="jobs"' in response.text


def test_static_assets_are_served():
    with TestClient(app) as client:
        for asset in ("app.js", "style.css"):
            response = client.get(f"/static/{asset}")
            assert response.status_code == 200, asset
            assert response.headers["content-type"].startswith(
                ("application/javascript", "text/javascript", "text/css")
            )


def test_dashboard_never_triggers_the_model():
    """Booting the app must not import torch or download checkpoints."""
    with TestClient(app) as client:
        health = client.get("/health").json()

    assert health["status"] == "ok"
    assert health["classifier"]["backend"] == "laya"
    # engine not instantiated yet: no download happened during startup/tests
    assert health["classifier"]["laya_ready"] is None
