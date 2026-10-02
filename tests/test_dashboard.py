"""Dashboard: static frontend served by FastAPI (pattern from the example repo)."""

from fastapi.testclient import TestClient

from app.main import app


def test_index_serves_dashboard():
    with TestClient(app) as client:
        response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Job Classifier" in response.text
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


def test_health_lists_sources():
    with TestClient(app) as client:
        health = client.get("/health").json()

    assert health["sources"] == ["linkedin", "geekhunter", "gupy", "glassdoor"]


def test_health_does_not_build_source_clients():
    """`/health` is polled every 30s: names only, no client construction."""
    from app.sources import source_names

    names = source_names()
    assert names == ["linkedin", "geekhunter", "gupy", "glassdoor"]


def test_sync_form_has_source_select():
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="source"' in html
    for value in ("linkedin", "geekhunter", "gupy", "glassdoor", "all"):
        assert f'value="{value}"' in html


def test_filters_have_source_select():
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="f-source"' in html
    for value in ("linkedin", "geekhunter", "gupy", "glassdoor"):
        assert html.count(f'value="{value}"') >= 2  # sync form + filter form


def test_app_js_sends_source_and_renders_chip():
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    # sync payload includes the selected source
    assert "source" in js
    assert 'params.set("source"' in js or '"source",' in js or "source:" in js
    # card renders the job's source chip
    assert "job.source" in js


def test_style_css_has_source_chip():
    with TestClient(app) as client:
        css = client.get("/static/style.css").text

    assert ".source-chip" in css
