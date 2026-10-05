"""GET/PUT /curriculum — optional file, atomic write, 422 ceiling (CA13, R8).

The curriculum lives in its own file, never inside `profile.json`: `PUT /profile`
serializes only the `ProfileOut` fields, so a shared file would be wiped on the
first profile save. These tests pin that independence.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import MAX_CURRICULUM_BYTES, app
from app.services import curriculum

VALID_PROFILE = {
    "name": "Test",
    "titles": ["SRE"],
    "seniority": ["Senior"],
    "locations": ["Brazil"],
    "remote_required": True,
    "skills": ["Kubernetes"],
    "focus": ["SRE"],
    "exclusions": ["english"],
}

MARKDOWN = "# Candidate\n\n## Skills\n- Kubernetes, Terraform\n"


@pytest.fixture()
def isolated_files(tmp_path, monkeypatch):
    """Both files in a tmp dir: the repo's data/ is never written."""
    profile = tmp_path / "profile.json"
    profile.write_text(json.dumps(VALID_PROFILE), encoding="utf-8")
    curriculum_file = tmp_path / "curriculum.md"

    monkeypatch.setattr(settings, "profile_path", str(profile))
    monkeypatch.setattr(curriculum, "DEFAULT_PATH", str(curriculum_file))
    return profile, curriculum_file


def test_get_curriculum_without_file_is_empty_not_404(isolated_files):
    """CA1: absent curriculum is a valid state, not an error."""
    _, curriculum_file = isolated_files
    assert not curriculum_file.exists()

    with TestClient(app) as client:
        response = client.get("/curriculum")

    assert response.status_code == 200
    assert response.json() == {"content": "", "version": None}


def test_put_then_get_round_trips_the_markdown(isolated_files):
    _, curriculum_file = isolated_files

    with TestClient(app) as client:
        saved = client.put("/curriculum", json={"content": MARKDOWN})
        assert saved.status_code == 200
        assert saved.json()["content"] == MARKDOWN
        assert curriculum_file.read_text(encoding="utf-8") == MARKDOWN

        fetched = client.get("/curriculum")

    assert fetched.json()["content"] == MARKDOWN
    assert fetched.json()["version"] == saved.json()["version"]


def test_put_returns_the_content_hash_as_version(isolated_files):
    import hashlib

    with TestClient(app) as client:
        response = client.put("/curriculum", json={"content": MARKDOWN})

    expected = hashlib.sha256(MARKDOWN.encode("utf-8")).hexdigest()
    assert response.json()["version"] == expected


def test_same_content_returns_the_same_version(isolated_files):
    """The version is the hash of the content, not of the save."""
    with TestClient(app) as client:
        first = client.put("/curriculum", json={"content": MARKDOWN})
        second = client.put("/curriculum", json={"content": MARKDOWN})

    assert first.json()["version"] == second.json()["version"]


def test_changed_content_returns_a_new_version(isolated_files):
    with TestClient(app) as client:
        first = client.put("/curriculum", json={"content": MARKDOWN})
        second = client.put("/curriculum", json={"content": MARKDOWN + "\nmore\n"})

    assert first.json()["version"] != second.json()["version"]


def test_oversized_payload_is_422_and_leaves_the_file_untouched(isolated_files):
    """The ceiling is checked before anything is written."""
    _, curriculum_file = isolated_files
    with TestClient(app) as client:
        client.put("/curriculum", json={"content": MARKDOWN})
        before = curriculum_file.read_text(encoding="utf-8")

        response = client.put("/curriculum", json={"content": "x" * (MAX_CURRICULUM_BYTES + 1)})

        assert response.status_code == 422
        assert curriculum_file.read_text(encoding="utf-8") == before
        assert client.get("/curriculum").json()["content"] == MARKDOWN


def test_payload_at_the_ceiling_is_accepted(isolated_files):
    """The bound is inclusive: exactly MAX_CURRICULUM_BYTES passes."""
    at_limit = "x" * MAX_CURRICULUM_BYTES

    with TestClient(app) as client:
        response = client.put("/curriculum", json={"content": at_limit})

    assert response.status_code == 200


def test_empty_content_is_accepted_and_clears_the_file(isolated_files):
    """An empty curriculum is how the user removes it."""
    _, curriculum_file = isolated_files
    with TestClient(app) as client:
        client.put("/curriculum", json={"content": MARKDOWN})
        response = client.put("/curriculum", json={"content": ""})

        assert response.status_code == 200
        assert curriculum_file.read_text(encoding="utf-8") == ""
        # The file exists, so the version is the hash of the empty content.
        assert response.json()["version"] is not None


def test_put_curriculum_leaves_no_temp_files_behind(isolated_files):
    _, curriculum_file = isolated_files

    with TestClient(app) as client:
        client.put("/curriculum", json={"content": MARKDOWN})

    leftovers = list(curriculum_file.parent.glob("curriculum.md.*"))
    assert leftovers == [], leftovers


def test_put_profile_does_not_erase_the_curriculum(isolated_files):
    """CA13: the whole reason the curriculum has its own file.

    `PUT /profile` rewrites `profile.json` from the `ProfileOut` fields only —
    any key outside the schema would be dropped on that save.
    """
    profile, curriculum_file = isolated_files
    with TestClient(app) as client:
        client.put("/curriculum", json={"content": MARKDOWN})

        response = client.put("/profile", json={**VALID_PROFILE, "name": "Renamed"})

        assert response.status_code == 200
        assert json.loads(profile.read_text(encoding="utf-8"))["name"] == "Renamed"
        # Both the API view and the bytes on disk keep the curriculum.
        assert client.get("/curriculum").json()["content"] == MARKDOWN
        assert curriculum_file.read_text(encoding="utf-8") == MARKDOWN


def test_put_curriculum_does_not_disturb_the_profile(isolated_files):
    """The reverse direction: saving the résumé leaves profile.json alone."""
    profile, _ = isolated_files
    before = profile.read_text(encoding="utf-8")

    with TestClient(app) as client:
        client.put("/curriculum", json={"content": MARKDOWN})

    assert profile.read_text(encoding="utf-8") == before


def test_profile_payload_still_works_with_no_curriculum_file(isolated_files):
    """CA1/R1: no curriculum on disk is a supported state everywhere."""
    _, curriculum_file = isolated_files
    with TestClient(app) as client:
        assert client.put("/profile", json=VALID_PROFILE).status_code == 200
        assert client.get("/curriculum").json()["version"] is None

    assert not curriculum_file.exists()
