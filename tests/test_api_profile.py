"""PUT /profile — validate, write atomically, never touch the file on 422."""

import json

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

VALID = {
    "name": "Test",
    "titles": ["SRE"],
    "seniority": ["Senior"],
    "locations": ["Brazil"],
    "remote_required": True,
    "skills": ["Kubernetes"],
    "focus": ["SRE"],
    "exclusions": ["english"],
}


@pytest.fixture()
def profile_file(tmp_path, monkeypatch):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(VALID), encoding="utf-8")
    monkeypatch.setattr(settings, "profile_path", str(path))
    return path


def test_put_profile_writes_file_and_get_returns_it(profile_file):
    payload = {**VALID, "name": "Updated", "skills": ["Terraform", "AWS"]}
    with TestClient(app) as client:
        response = client.put("/profile", json=payload)
        assert response.status_code == 200
        assert response.json()["name"] == "Updated"
        on_disk = json.loads(profile_file.read_text(encoding="utf-8"))
        assert on_disk["skills"] == ["Terraform", "AWS"]
        assert client.get("/profile").json()["name"] == "Updated"


def test_put_profile_invalid_payload_422_and_file_unchanged(profile_file):
    before = profile_file.read_text(encoding="utf-8")
    with TestClient(app) as client:
        response = client.put("/profile", json={**VALID, "skills": "not-a-list"})
        assert response.status_code == 422
    assert profile_file.read_text(encoding="utf-8") == before


def test_put_profile_missing_required_field_422(profile_file):
    before = profile_file.read_text(encoding="utf-8")
    payload = {key: value for key, value in VALID.items() if key != "remote_required"}
    with TestClient(app) as client:
        response = client.put("/profile", json=payload)
        assert response.status_code == 422
    assert profile_file.read_text(encoding="utf-8") == before


def test_put_profile_empty_skills_is_accepted(profile_file):
    with TestClient(app) as client:
        response = client.put("/profile", json={**VALID, "skills": []})
    assert response.status_code == 200
    assert json.loads(profile_file.read_text(encoding="utf-8"))["skills"] == []
