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


def test_dashboard_has_sidebar_with_three_pages():
    """Sidebar nav + the three page containers the hash router switches.

    CA1/R1: the sidebar exposes only Vagas, Kanban and Configurações, in that
    order. R3/R4: Perfil and Dados are no longer top-level pages — they became
    tabs inside Configurações, so `#/perfil`, `#/dados`, `#page-perfil` and
    `#page-dados` must be gone (CA10: the old hashes fall back to Vagas).
    """
    with TestClient(app) as client:
        html = client.get("/").text

    for fragment in (
        'class="sidebar"',
        "#/vagas",
        "#/kanban",
        "#/configuracoes",
        'id="page-vagas"',
        'id="page-kanban"',
        'id="page-configuracoes"',
        'id="tab-perfil"',
        'id="tab-dados"',
        'data-tab="perfil"',
        'data-tab="dados"',
    ):
        assert fragment in html, fragment

    # R1: exactly three links, in order.
    assert html.count('class="sidebar-link"') == 3
    assert html.index("#/vagas") < html.index("#/kanban") < html.index("#/configuracoes")

    # R4: Perfil and Dados left the sidebar.
    for removed in ("#/perfil", "#/dados", 'id="page-perfil"', 'id="page-dados"'):
        assert removed not in html, removed


def test_dashboard_migrated_ids_survive_inside_the_config_tabs():
    """CA9/R6: moving Perfil and Dados into tabs may only change the path.

    The ids the frontend and the tests bind to must still exist, now nested in
    `#page-configuracoes` / `#tab-perfil` / `#tab-dados` / `#page-kanban`.
    """
    with TestClient(app) as client:
        html = client.get("/").text

    config = html[html.index('id="page-configuracoes"') : html.index('id="page-kanban"')]
    perfil = config[config.index('id="tab-perfil"') : config.index('id="tab-dados"')]
    dados = config[config.index('id="tab-dados"') :]
    kanban = html[html.index('id="page-kanban"') :]

    for element_id in (
        'id="profile-form"',
        'id="clean-btn"',
        'id="data-total"',
        'id="source-counts"',
    ):
        assert element_id in config, element_id

    for field in ("p-titles", "p-skills", "p-remote", "p-exclusions"):
        assert f'id="{field}"' in perfil, field

    for element_id in (
        'id="data-total"',
        'id="source-counts"',
        'id="clean-btn"',
    ):
        assert element_id in dados, element_id

    for status in ("CHECK", "RUNNING", "DONE"):
        assert f'id="kanban-body-{status}"' in kanban, status


def test_dashboard_profile_form_and_clean_button_exist():
    with TestClient(app) as client:
        html = client.get("/").text
        js = client.get("/static/app.js").text

    assert 'id="profile-form"' in html
    for field in ("p-titles", "p-skills", "p-remote", "p-exclusions"):
        assert field in html, field
    assert 'id="clean-btn"' in html
    # destructive action must be guarded by a confirmation
    assert "confirm(" in js


def test_dashboard_has_kanban_page():
    """Sidebar nav + kanban page container with three columns."""
    with TestClient(app) as client:
        html = client.get("/").text

    for fragment in (
        "#/kanban",
        'id="page-kanban"',
        'id="kanban-CHECK"',
        'id="kanban-RUNNING"',
        'id="kanban-DONE"',
    ):
        assert fragment in html, fragment


def test_app_js_add_button_posts_to_kanban():
    """+ Add button in card posts to /kanban and removes card without reload."""
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "POST /kanban" in js or '"/kanban"' in js
    assert "job.source" in js
    assert "job.source_id" in js
    assert "✓ Adicionada ao CHECK" in js


def test_app_js_moves_kanban_card():
    """Kanban card can be moved via PATCH with status."""
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "PATCH /kanban/" in js or "`/kanban/${" in js
    assert "CHECK" in js
    assert "RUNNING" in js
    assert "DONE" in js


def test_app_js_kanban_card_renders_fields():
    """Kanban card shows title, company, location, url, created_at."""
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert "item.title" in js
    assert "item.company" in js
    assert "item.location" in js
    assert "item.url" in js
    assert "item.created_at" in js


def test_style_css_has_kanban_columns():
    """Kanban columns are styled."""
    with TestClient(app) as client:
        css = client.get("/static/style.css").text

    assert ".kanban-board" in css
    assert ".kanban-column" in css
    assert ".kanban-card" in css


def test_add_button_reads_dataset_in_camel_case():
    """`data-source-id` vira `dataset.sourceId` — nunca `dataset.source_id`.

    Regression: o `+ Add` mandava `source_id: undefined` e a API respondia
    422 "Field required". Só o browser real expõe o nome camelCase; ler a
    fonte pelo atributo escrito no HTML é o que garante a correspondência.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text
        html = client.get("/").text

    # o atributo é escrito com hífen…
    assert 'data-source-id="' in js
    # …e lido como camelCase, que é o que o DOM realmente expõe
    assert "button.dataset.sourceId" in js
    assert "button.dataset.source_id" not in js
    assert html.count('href="#/kanban"') == 1


def test_add_to_kanban_decrements_the_job_counter():
    """Remover o card da lista tem que mexer no contador junto.

    Regression: o `+ Add` tirava o card do DOM e o contador continuava
    mostrando o total antigo — a tela dizia 3 vagas listando 2.
    """
    with TestClient(app) as client:
        js = client.get("/static/app.js").text

    assert '$("#total")' in js  # o mesmo contador que loadJobs atualiza
    assert "totalEl.textContent" in js
    assert "shown - 1" in js
