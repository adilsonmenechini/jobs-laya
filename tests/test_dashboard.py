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

    assert health["sources"] == ["linkedin", "geekhunter", "gupy", "indeed", "glassdoor"]


def test_health_does_not_build_source_clients():
    """`/health` is polled every 30s: names only, no client construction."""
    from app.sources import source_names

    names = source_names()
    assert names == ["linkedin", "geekhunter", "gupy", "indeed", "glassdoor"]


def test_sync_form_has_source_select():
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="source"' in html
    for value in ("linkedin", "geekhunter", "gupy", "indeed", "glassdoor", "all"):
        assert f'value="{value}"' in html


def test_filters_have_source_select():
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="f-source"' in html
    for value in ("linkedin", "geekhunter", "gupy", "indeed", "glassdoor"):
        assert html.count(f'value="{value}"') >= 2  # sync form + filter form


def test_app_js_sends_source_and_renders_chip():
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    # sync payload includes the selected source
    assert "source" in js
    assert 'params.set("source"' in js or '"source",' in js or "source:" in js
    # card renders the job's source chip
    assert "job.source" in js


def test_app_js_surfaces_pydantic_array_detail():
    """A 422 carries `detail` as a **list** of error objects, not a string.

    Regression: `getJSON` only read `detail` when it was a string, so the card
    showed `Erro: Unprocessable Content` instead of the field message.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "Array.isArray" in js  # the list shape is handled explicitly
    assert ".map(" in js and ".msg" in js  # each item's msg is read out
    assert "res.statusText" in js  # remains the last-resort fallback


def test_app_js_renders_posted_at():
    """The card shows the posting date so the recency window is visible."""
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "job.posted_at" in js


def test_app_js_formats_posted_at_before_rendering():
    """`posted_at` reaches the card as a raw string.

    The Gupy source sends a full ISO timestamp (`2026-10-01T12:37:19.873Z`)
    while other sources send `YYYY-MM-DD` or relative text (`Publicada há 5
    dias`). Rendering it raw overflowed the card — the date must go through
    `formatPostedAt()`.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "function formatPostedAt" in js
    # the card renders the formatted value, never the raw column
    assert "formatPostedAt(job.posted_at)" in js
    assert "esc(job.posted_at)" not in js
    # ISO datetime is cut down to its date part
    assert ".slice(0, 10)" in js


def test_sync_form_has_hours_old_select():
    """The recency window is chosen in the front: 1d · 72h · 7d · 30d · todas."""
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="hours-old"' in html
    for value in ("24", "72", "168", "720", "0"):
        assert f'<option value="{value}"' in html
    assert '<option value="720" selected' in html  # default: 30 dias


def test_app_js_sends_hours_old():
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "hours_old" in js  # payload carries the selected window


def test_style_css_has_source_chip():
    with TestClient(app) as client:
        css = client.get("/static/style.css").text

    assert ".source-chip" in css


def test_app_js_shows_low_match_indicator():
    """Low match jobs should show a prominent indicator with the reason."""
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "low-indicator" in js
    assert "low-match" in js


def test_app_js_low_indicator_reads_the_gap_array_not_the_joined_html():
    """`gaps` is joined HTML (`<li>…`), so `gaps[0]` renders as '<'.

    Regression: the indicator used to show `⚠️ <` on every low card.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "gaps[0]" not in js
    assert "gapList[0]" in js  # first gap taken from the raw array


def test_style_css_has_low_match_indicator():
    """Low match indicator should be styled prominently."""
    with TestClient(app) as client:
        css = client.get("/static/style.css").text

    assert ".low-indicator" in css
    assert ".card.low-match" in css
    assert "border-color: var(--low)" in css


def test_dashboard_gives_every_control_an_accessible_name():
    """axe-core `select-name` / `label-title-only`: the filter selects used to
    carry no name at all, and the sync form relied on `title` only.
    """
    with TestClient(app) as client:
        html = client.get("/").text

    # the three filter selects (they have no <label> by design — no build step)
    for control_id in ("f-source", "f-match", "f-remote"):
        tag = next(line for line in html.splitlines() if f'id="{control_id}"' in line)
        assert "aria-label=" in tag, control_id

    # every sync-form control needs a name too
    for control_id in ("source", "keywords", "location", "limit", "hours-old"):
        tag = next(line for line in html.splitlines() if f'id="{control_id}"' in line)
        assert "aria-label=" in tag, control_id


def test_dashboard_content_lives_inside_a_landmark():
    """axe-core `region`: the panels used to sit outside any landmark."""
    with TestClient(app) as client:
        html = client.get("/").text

    assert "<main>" in html
    # a single <main>, opened before the panels and closed after #jobs
    assert html.count("<main>") == 1
    assert html.index("<main>") < html.index('id="sync-form"')
    assert html.index('id="jobs"') < html.index("</main>")


def test_style_css_badge_colors_meet_contrast():
    """axe-core `color-contrast`: `--low` at 4.00 and `--high` at 3.68 fell
    below the 4.5:1 minimum against the card tint."""
    with TestClient(app) as client:
        css = client.get("/static/style.css").text

    assert "--low: #ff7b72" in css  # 4.98:1 on its own tint
    assert "--high: #56d364" in css  # 6.04:1 on its own tint
    # the tints are derived from the same colours, not the old ones
    assert "rgba(248, 81, 73" not in css
    assert "rgba(46, 160, 67" not in css


def test_filters_have_location_input():
    """Dashboard has a location filter input."""
    with TestClient(app) as client:
        html = client.get("/").text

    assert 'id="f-location"' in html


def test_app_js_sends_location_filter():
    """Frontend sends location filter to API."""
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "f-location" in js
    assert 'params.set("location"' in js


def test_app_js_footer_opens_with_the_real_backend():
    """The card footer hard-coded `Laya ·` as its prefix.

    A sync under `CLASSIFIER_BACKEND=fake` therefore rendered
    `Laya · modelo fake · 1 ms · backend laya` — the family name asserted
    itself over the provenance it was supposed to report.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "Laya · modelo" not in js
    assert "backend ${esc(laya.backend)} · modelo ${esc(laya.model)}" in js


def test_app_js_labels_the_badge_as_the_active_backend():
    """The badge reports the running config, the cards report provenance.

    Unlabelled, the two read as a contradiction: a process pointed at `fake`
    sitting above cards classified by `laya`. The badge must say which of the
    two it is.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "backend ativa: " in js
    # the tooltip spells out where the card's own backend comes from
    assert "classificou" in js
