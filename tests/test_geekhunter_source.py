"""GeekHunterSource HTTP behavior — httpx.MockTransport, no network."""

import httpx
import pytest

from app.config import Settings
from app.sources import SourceUnavailableError
from app.sources.geekhunter import GeekHunterSource
from tests.fixtures_loader import fixture

SEARCH = fixture("geekhunter_search.html")
DETAIL = fixture("geekhunter_job_detail.html")


def make_source(handler) -> GeekHunterSource:
    config = Settings(
        _env_file=None,
        geekhunter_base_url="https://geekhunter.test",
        geekhunter_delay_seconds=0.0,
        geekhunter_page_size=25,
    )
    client = httpx.AsyncClient(
        base_url=config.geekhunter_base_url,
        transport=httpx.MockTransport(handler),
    )
    return GeekHunterSource(config, client=client)


@pytest.mark.asyncio
async def test_search_returns_normalized_items():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=SEARCH)

    source = make_source(handler)
    items = await source.search("SRE", "Brazil", limit=10)

    assert len(items) == 10
    assert items[0]["source"] == "geekhunter"
    assert items[0]["source_id"] == "site-reliability-engineer--sre--3"
    assert "searchTerm=SRE" in seen[0]
    # Brazil is not a city: cityName must not be sent
    assert "cityName" not in seen[0]


@pytest.mark.asyncio
async def test_search_sends_real_city_as_cityname():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(200, text=SEARCH)

    source = make_source(handler)
    await source.search("SRE", "Florianópolis", limit=5)

    assert "cityName=Florian" in seen[0]


@pytest.mark.asyncio
async def test_search_paginates_until_batch_is_short():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        pages.append(page)
        if page == "1":
            return httpx.Response(200, text=SEARCH)
        return httpx.Response(200, text="<html><body>no jobs</body></html>")

    # page_size == fixture batch (17): first page looks full → must fetch page 2
    config = Settings(
        _env_file=None,
        geekhunter_base_url="https://geekhunter.test",
        geekhunter_delay_seconds=0.0,
        geekhunter_page_size=17,
    )
    client = httpx.AsyncClient(
        base_url=config.geekhunter_base_url,
        transport=httpx.MockTransport(handler),
    )
    source = GeekHunterSource(config, client=client)
    items = await source.search("SRE", "Brazil", limit=100)

    # second page is empty: stop without duplicating
    assert len(items) == 17
    assert pages == ["1", "2"]


@pytest.mark.asyncio
async def test_search_stops_when_batch_shorter_than_page_size():
    pages = []

    def handler(request: httpx.Request) -> httpx.Response:
        pages.append(request.url.params.get("page", "1"))
        return httpx.Response(200, text=SEARCH)

    source = make_source(handler)  # page_size 25 > fixture's 17 cards
    items = await source.search("SRE", "Brazil", limit=100)

    assert len(items) == 17
    assert pages == ["1"]  # short batch = last page, no extra request


@pytest.mark.asyncio
async def test_search_wraps_network_errors():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    source = make_source(handler)
    with pytest.raises(SourceUnavailableError):
        await source.search("SRE", "Brazil")


# --------------------------------------------------------------------- retry


@pytest.mark.asyncio
async def test_search_retries_transient_failures_then_succeeds(monkeypatch):
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ConnectError("blip", request=request)
        return httpx.Response(200, text=SEARCH)

    monkeypatch.setattr("app.sources.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.retry.random.uniform", lambda low, high: 0.0)

    source = make_source(handler)
    source._config.geekhunter_max_retries = 2
    source._config.geekhunter_backoff_seconds = 5.0
    items = await source.search("SRE", "Brazil", limit=5)

    assert len(items) == 5
    assert len(calls) == 3
    assert slept == [5.0, 10.0]


@pytest.mark.asyncio
async def test_search_raises_after_exhausting_retries(monkeypatch):
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr("app.sources.retry.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.retry.random.uniform", lambda low, high: 0.0)

    source = make_source(handler)
    source._config.geekhunter_max_retries = 2
    source._config.geekhunter_backoff_seconds = 5.0
    with pytest.raises(SourceUnavailableError, match="request failed"):
        await source.search("SRE", "Brazil")

    assert len(calls) == 3
    assert slept == [5.0, 10.0]


@pytest.mark.asyncio
async def test_search_does_not_retry_permanent_errors(monkeypatch):
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(400, text="bad request")

    monkeypatch.setattr("app.sources.retry.asyncio.sleep", fake_sleep)
    source = make_source(handler)
    source._config.geekhunter_max_retries = 3
    source._config.geekhunter_backoff_seconds = 5.0

    with pytest.raises(SourceUnavailableError):
        await source.search("SRE", "Brazil")

    assert len(calls) == 1
    assert slept == []


@pytest.mark.asyncio
async def test_details_merges_without_wiping_search_data():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=DETAIL)

    source = make_source(handler)
    item = {
        "source": "geekhunter",
        "source_id": "site-reliability-engineer--sre--3",
        "title": "Analista - Site Reliability Engineer (SRE)",
        "company": None,
        "location": "São Paulo, SP, Brasil",  # search-only data
        "remote": False,
        "url": ("https://www.geekhunter.com/pt/ntt-data/jobs/site-reliability-engineer--sre--3"),
        "description": "excerpt from card",
        "posted_at": "Atualizada há 20 minutos",
        "raw": {"modality": "Remoto"},
    }
    merged = await source.details(item)

    assert merged["company"] == "NTT DATA"
    assert "dynatrace" in merged["description"]
    assert merged["location"] == "São Paulo, SP, Brasil"  # detail has none: kept
    assert merged["posted_at"] == "2026-09-30"  # ISO date from JobPosting wins
    assert merged["remote"] is True  # upgraded


@pytest.mark.asyncio
async def test_details_without_url_is_noop():
    source = make_source(lambda request: httpx.Response(500))
    item = {"source": "geekhunter", "source_id": "x", "title": "T"}

    assert await source.details(item) == item


@pytest.mark.asyncio
async def test_details_upstream_error_propagates_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    source = make_source(handler)
    with pytest.raises(SourceUnavailableError):
        await source.details({"source_id": "x", "url": "https://geekhunter.test/pt/a/jobs/x-1"})
