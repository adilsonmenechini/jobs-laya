"""API tests for the /tools endpoints (fake client injected via dependency)."""

import pytest
from fastapi.testclient import TestClient

from app.linkedin.tools import LinkedInTools, ToolError, ToolNotFoundError, get_tools
from app.main import app
from tests.test_tools import DETAIL_PAYLOAD, SEARCH_PAYLOAD, FakeClient


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def use_fake_client(fake: FakeClient) -> None:
    app.dependency_overrides[get_tools] = lambda: LinkedInTools(client=fake)


def test_tools_registry_lists_read_only_job_tools(client):
    response = client.get("/tools")
    assert response.status_code == 200
    body = response.json()
    names = [tool["name"] for tool in body["tools"]]
    assert names == ["search_jobs", "get_job_details", "get_saved_jobs"]
    for tool in body["tools"]:
        assert tool["description"]
        assert tool["input_schema"]["properties"]


def test_search_jobs_endpoint(client):
    use_fake_client(FakeClient(search=SEARCH_PAYLOAD))

    response = client.post(
        "/tools/search_jobs",
        json={"keywords": "SRE", "location": "Brazil", "limit": 2},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["tool"] == "search_jobs"
    assert body["count"] == 2
    assert body["items"][0]["linkedin_id"] == "123"


def test_search_jobs_validates_input(client):
    response = client.post("/tools/search_jobs", json={"keywords": ""})
    assert response.status_code == 422

    response = client.post("/tools/search_jobs", json={"keywords": "SRE", "limit": 0})
    assert response.status_code == 422


def test_get_job_details_endpoint(client):
    use_fake_client(FakeClient(detail=DETAIL_PAYLOAD))

    response = client.get("/tools/get_job_details/123")

    assert response.status_code == 200
    body = response.json()
    assert body["tool"] == "get_job_details"
    assert body["item"]["title"] == "Senior SRE"


def test_get_saved_jobs_endpoint(client):
    use_fake_client(FakeClient(saved={"results": [{"id": "77", "title": "Staff SRE"}]}))

    response = client.get("/tools/get_saved_jobs?limit=5")

    assert response.status_code == 200
    body = response.json()
    assert body["tool"] == "get_saved_jobs"
    assert body["count"] == 1


def test_upstream_failure_maps_to_502(client):
    use_fake_client(FakeClient(error=RuntimeError("browser not ready")))

    response = client.post("/tools/search_jobs", json={"keywords": "SRE"})

    assert response.status_code == 502
    assert "browser not ready" in response.json()["detail"]


def test_unknown_job_maps_to_404(client):
    use_fake_client(FakeClient(detail={"jobs": []}))

    response = client.get("/tools/get_job_details/nope")

    assert response.status_code == 404


def test_tool_error_types_are_distinct():
    assert issubclass(ToolNotFoundError, ToolError)
    assert get_tools().__class__ is LinkedInTools
