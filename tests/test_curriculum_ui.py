"""Currículo in Configurações → Perfil: markup served, JS wired (CA14, R10).

The end-to-end browser pass (typing in the textarea, saving, reloading) belongs
to the REVIEW; these tests pin what the suite can assert without a browser — the
markup exists, sits inside the Perfil tab, and the JS reads and writes it through
the documented endpoints.
"""

from fastapi.testclient import TestClient

from app.main import app


def _assets() -> tuple[str, str]:
    with TestClient(app) as client:
        return client.get("/").text, client.get("/static/app.js").text


def test_curriculum_form_exists_with_a_labeled_textarea():
    """The field must be reachable and named, not a bare input."""
    html, _ = _assets()

    assert 'id="curriculum-form"' in html
    assert 'id="curriculum-md"' in html
    assert "<textarea" in html
    assert 'for="curriculum-md"' in html
    assert 'aria-label="currículo em markdown"' in html


def test_curriculum_form_lives_inside_the_perfil_tab():
    """R10: it belongs to the Perfil tab of Configurações, not to its own page."""
    html, _ = _assets()

    tab_perfil = html.index('id="tab-perfil"')
    tab_dados = html.index('id="tab-dados"')
    form = html.index('id="curriculum-form"')

    assert tab_perfil < form < tab_dados


def test_save_button_and_live_region_status_exist():
    html, _ = _assets()

    assert "Currículo" in html
    assert 'id="curriculum-status"' in html
    # the status is announced, not silently swapped
    assert 'role="status"' in html
    assert 'aria-live="polite"' in html


def test_js_loads_the_curriculum_into_the_textarea():
    _, js = _assets()

    assert "loadCurriculum" in js
    assert 'getJSON("/curriculum")' in js
    assert '$("#curriculum-md").value' in js


def test_js_saves_the_textarea_via_put():
    _, js = _assets()

    assert "saveCurriculum" in js
    assert 'method: "PUT"' in js
    assert 'content: $("#curriculum-md").value' in js


def test_submitting_the_curriculum_form_is_wired_to_save():
    """A form without a submit listener silently does nothing on Enter/click."""
    _, js = _assets()

    assert '$("#curriculum-form").addEventListener("submit", saveCurriculum)' in js


def test_save_reports_success_and_failure_in_the_status():
    _, js = _assets()

    assert "Currículo salvo com sucesso." in js
    assert "Erro ao carregar currículo" in js


def test_curriculum_load_is_called_when_a_tab_opens():
    """The Perfil tab must load the résumé, like it loads the profile."""
    _, js = _assets()

    assert "loadCurriculum()" in js


def test_no_file_upload_input_was_introduced():
    """Decision 3 of the SPEC: a text field, not an upload."""
    html, _ = _assets()

    assert 'type="file"' not in html
    assert "/curriculum/upload" not in html
