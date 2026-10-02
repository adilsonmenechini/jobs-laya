"""GupySource — public HTTP API, read-only (fixtures, no network).

TDD: written before `app/sources/gupy.py` (spec FR-1 / FR-4).
"""

import json

import httpx
import pytest

from app.config import Settings
from app.sources import SourceUnavailableError
from app.sources.gupy import GupySource, location_params, normalize_item, parse_detail
from tests.fixtures_loader import fixture

SEARCH = json.loads(fixture("gupy_search.json"))
DETAIL = fixture("gupy_job_detail.html")


def make_source(handler, **overrides) -> GupySource:
    defaults: dict = {
        "gupy_base_url": "https://gupy.test",
        "gupy_delay_seconds": 0.0,
        "gupy_page_size": 10,
    }
    defaults.update(overrides)
    config = Settings(_env_file=None, **defaults)
    client = httpx.AsyncClient(
        base_url=config.gupy_base_url, transport=httpx.MockTransport(handler)
    )
    return GupySource(config, client=client)


# --------------------------------------------------------------- location map


def test_location_empty_and_brazil_send_no_filter():
    for value in ("", "   ", "Brazil", "brasil", "BRASIL"):
        assert location_params(value) == {}


def test_location_remoto_maps_to_workplace_type_not_city():
    # Gotcha: "remoto" is not a city upstream — never send it as city.
    for value in ("remoto", "Remote", " REMOTO "):
        assert location_params(value) == {"workplaceType": "remote"}


def test_location_full_state_name_maps_to_state():
    assert location_params("bahia") == {"state": "Bahia"}
    assert location_params("SÃO PAULO") == {"state": "São Paulo"}
    assert location_params("distrito federal") == {"state": "Distrito Federal"}


def test_location_anything_else_maps_to_city():
    assert location_params("Curitiba") == {"city": "Curitiba"}
    assert location_params("Florianópolis") == {"city": "Florianópolis"}


# --------------------------------------------------------------------- search


@pytest.mark.asyncio
async def test_search_returns_normalized_items():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, json=SEARCH)

    source = make_source(handler)
    items = await source.search("devops", "Brazil", limit=10)

    assert len(items) == 4
    first = items[0]
    assert first["source"] == "gupy"
    assert first["source_id"] == "12650308"
    assert first["title"] == "DevOps Engineer"
    assert first["company"] == "SoftDesign"
    assert first["remote"] is True
    assert first["location"] == ""  # remote payload carries no city/state
    assert first["url"] == SEARCH["data"][0]["jobUrl"]
    assert "Buscamos" in first["description"]
    assert first["posted_at"] == "2026-10-01T13:23:13.263Z"
    assert first["raw"]["id"] == 12650308
    assert "jobName=devops" in seen[0]


@pytest.mark.asyncio
async def test_search_location_filters_go_to_the_right_param():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(dict(request.url.params))
        return httpx.Response(200, json=SEARCH)

    source = make_source(handler)

    await source.search("devops", "remoto")
    assert seen[0]["workplaceType"] == "remote"
    assert "city" not in seen[0] and "state" not in seen[0]

    await source.search("devops", "Bahia")
    assert seen[1]["state"] == "Bahia"
    assert "city" not in seen[1] and "workplaceType" not in seen[1]

    await source.search("devops", "Curitiba")
    assert seen[2]["city"] == "Curitiba"
    assert "state" not in seen[2] and "workplaceType" not in seen[2]

    await source.search("devops", "Brazil")
    assert not {"city", "state", "workplaceType"} & set(seen[3])


@pytest.mark.asyncio
async def test_search_location_builds_city_uf_string():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=SEARCH)

    items = await make_source(handler).search("devops", "Brazil", limit=10)

    assert items[0]["location"] == ""  # remote: city and state empty
    assert items[1]["location"] == "Brasília - DF"
    assert items[2]["location"] == "Santiago"  # city only, no Brazilian state
    assert items[3]["location"] == "São Paulo - SP"
    assert items[2]["remote"] is False
    assert items[3]["remote"] is False


@pytest.mark.asyncio
async def test_search_paginates_by_offset_until_limit():
    offsets = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "10"))
        offsets.append(offset)
        page = SEARCH["data"][offset : offset + limit]
        return httpx.Response(200, json={"data": page, "pagination": {}})

    source = make_source(handler, gupy_page_size=2)
    items = await source.search("devops", "", limit=3)

    assert [item["source_id"] for item in items] == ["12650308", "12198836", "12607005"]
    assert offsets == [0, 2]  # 4 < limit stops the loop before a third request


@pytest.mark.asyncio
async def test_search_stops_on_short_page():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=SEARCH)  # 4 items, page_size 10

    source = make_source(handler)
    items = await source.search("devops", "", limit=100)

    assert len(items) == 4
    assert len(calls) == 1  # short batch = last page


@pytest.mark.asyncio
async def test_search_stops_on_empty_page():
    offsets = []

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params.get("offset", "0"))
        limit = int(request.url.params.get("limit", "10"))
        offsets.append(offset)
        page = SEARCH["data"][offset : offset + limit]
        return httpx.Response(200, json={"data": page, "pagination": {}})

    source = make_source(handler, gupy_page_size=2)
    items = await source.search("devops", "", limit=100)

    assert len(items) == 4
    assert offsets == [0, 2, 4]  # offset 4 is past the data → empty page stops it


@pytest.mark.asyncio
async def test_search_wraps_network_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(SourceUnavailableError):
        await make_source(handler).search("devops", "")


@pytest.mark.asyncio
async def test_search_wraps_http_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="upstream exploded")

    with pytest.raises(SourceUnavailableError):
        await make_source(handler).search("devops", "")


# ---------------------------------------------------------------- normalization


def test_normalize_item_truncates_posted_at_to_column_size():
    payload = {**SEARCH["data"][0], "publishedDate": "2026-10-01T13:23:13.263Z" + "x" * 200}

    item = normalize_item(payload)

    assert len(item["posted_at"]) == 100


def test_normalize_item_cleans_html_entities():
    payload = {**SEARCH["data"][0], "description": "R&amp;D&nbsp;team &lt;devs&gt;"}

    item = normalize_item(payload)

    assert item["description"] == "R&D team <devs>"


def test_normalize_item_state_only_location_uses_uf():
    payload = {**SEARCH["data"][0], "city": "", "state": "Bahia"}

    assert normalize_item(payload)["location"] == "BA"


# --------------------------------------------------------------------- details


@pytest.mark.asyncio
async def test_details_with_description_is_a_noop():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("details must not fetch when description exists")

    source = make_source(handler)
    item = {"source": "gupy", "source_id": "1", "title": "T", "description": "already there"}

    assert await source.details(item) is item


@pytest.mark.asyncio
async def test_details_fetches_and_strips_html():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=DETAIL)

    source = make_source(handler)
    item = {
        "source": "gupy",
        "source_id": "12650308",
        "title": "Search title wins",
        "company": "SoftDesign",
        "location": "São Paulo - SP",
        "remote": True,
        "url": SEARCH["data"][0]["jobUrl"],
        "description": "",
        "posted_at": None,
        "raw": {"id": 12650308},
    }

    merged = await source.details(item)

    assert "Buscamos" in merged["description"]
    assert "<p>" not in merged["description"]
    # partial-success: good search data is never wiped
    assert merged["title"] == "Search title wins"
    assert merged["location"] == "São Paulo - SP"
    assert merged["remote"] is True


@pytest.mark.asyncio
async def test_details_without_next_data_keeps_item():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>oops</body></html>")

    source = make_source(handler)
    item = {"source": "gupy", "source_id": "1", "title": "T", "description": "", "url": "https://x"}

    merged = await source.details(item)

    assert merged["description"] == ""
    assert merged["title"] == "T"


@pytest.mark.asyncio
async def test_details_without_url_is_a_noop():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("details must not fetch without a url")

    source = make_source(handler)
    item = {"source": "gupy", "source_id": "1", "title": "T"}

    assert await source.details(item) is item


@pytest.mark.asyncio
async def test_details_network_error_propagates_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    source = make_source(handler)
    with pytest.raises(SourceUnavailableError):
        await source.details({"source": "gupy", "source_id": "1", "url": "https://x/job/1"})


# ------------------------------------------------------------------- __NEXT_DATA__


def test_parse_detail_reads_description_from_next_data():
    description = parse_detail(DETAIL)

    assert description is not None
    assert "Buscamos" in description
    assert "<" not in description


def test_parse_detail_without_next_data_returns_none():
    assert parse_detail("<html><body>no data</body></html>") is None
