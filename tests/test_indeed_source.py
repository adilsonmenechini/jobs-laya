"""IndeedSource — public GraphQL API, read-only (fixtures, no network).

TDD: written before `app/sources/indeed.py`.

The SERP HTML carries no description and no posting date, which the classifier
needs, so the source talks to the same open JSON endpoint JobSpy uses
(`apis.indeed.com/graphql`): one request returns title, employer, location,
full description HTML, skills and the employer's apply URL.
"""

import json
from datetime import datetime

import httpx
import pytest

from app.config import Settings
from app.sources import SourceUnavailableError
from app.sources.indeed import (
    IndeedSource,
    location_arg,
    normalize_item,
    parse_response,
    strip_html,
)
from tests.fixtures_loader import fixture

SEARCH = json.loads(fixture("indeed_search.json"))
RESULTS = SEARCH["data"]["jobSearch"]["results"]


def make_source(handler, **overrides) -> IndeedSource:
    defaults: dict = {
        "indeed_base_url": "https://apis.indeed.test",
        "indeed_delay_seconds": 0.0,
        "indeed_page_size": 10,
        # single shot unless a retry test opts in — retries would otherwise
        # put real backoff sleeps inside the failure tests below.
        "indeed_max_retries": 0,
        # hermetic: Settings(_env_file=None) never reads the real .env
        "indeed_api_key": "test-key",
    }
    defaults.update(overrides)
    config = Settings(_env_file=None, **defaults)
    client = httpx.AsyncClient(
        base_url=config.indeed_base_url, transport=httpx.MockTransport(handler)
    )
    return IndeedSource(config, client=client)


# --------------------------------------------------------------- location map


def test_location_empty_and_brazil_send_no_filter():
    for value in ("", "   ", "Brazil", "brasil", "BRASIL"):
        assert location_arg(value) == ""


def test_location_remoto_becomes_remote_query():
    # Gotcha: Indeed has no "remote" filter param here — the query text carries it.
    for value in ("remoto", "Remote", " REMOTO "):
        assert location_arg(value) == "remoto"


def test_location_anything_else_is_passed_through():
    assert location_arg("Curitiba") == "Curitiba"
    assert location_arg("São Paulo, SP") == "São Paulo, SP"


# ---------------------------------------------------------------- normalization


def test_normalize_item_reads_the_contract_fields():
    item = normalize_item(RESULTS[1]["job"])

    assert item["source"] == "indeed"
    assert item["source_id"] == "6a29acc2c824b871"  # `key` is the stable id
    assert item["title"] == "Especialista em SRE"
    assert item["company"] == "Cielo Pagamentos"
    assert item["location"] == "Barueri, SP"
    assert item["remote"] is False
    assert item["url"].startswith("https://cielo.inhire.app/")
    assert "máquina" in item["description"]  # HTML entities decoded
    assert "<" not in item["description"]
    assert item["posted_at"] is not None
    assert item["raw"]["key"] == "6a29acc2c824b871"


def test_normalize_item_marks_remote_when_city_says_remoto():
    # Indeed BR reports remote jobs with city = "Remoto".
    item = normalize_item(RESULTS[2]["job"])

    assert item["location"] == "Remoto"
    assert item["remote"] is True


def test_normalize_item_without_employer_keeps_none():
    # The first result carries no `employer` object upstream.
    item = normalize_item(RESULTS[0]["job"])

    assert item["company"] is None
    assert item["title"] == "Engenheiro de Dados (Sênior)"
    # apply url still comes from `recruit` even without an employer
    assert item["url"].startswith("https://viciodeumaestudante.")


def test_normalize_item_falls_back_to_indeed_viewjob_url():
    # No employer and no apply link → the Indeed viewjob page is the home.
    job = {**RESULTS[1]["job"], "employer": None, "recruit": None}

    item = normalize_item(job)

    assert item["url"] == f"https://br.indeed.com/viewjob?jk={RESULTS[1]['job']['key']}"


def test_normalize_item_without_any_url_is_none():
    item = normalize_item({"title": "T"})  # no key, no recruit, no employer

    assert item["url"] is None
    assert item["company"] is None
    assert item["location"] is None
    assert item["posted_at"] is None
    assert item["remote"] is False


def test_normalize_item_skills_land_in_raw():
    item = normalize_item(RESULTS[1]["job"])

    assert "Sistemas de conteinerização" in item["raw"]["skills"]


def test_normalize_item_truncates_posted_at_to_column_size():
    payload = {**RESULTS[1]["job"], "datePublished": 1790917200000}

    item = normalize_item(payload)

    assert len(item["posted_at"]) <= 100


def test_normalize_item_posted_at_is_iso_date():
    item = normalize_item(RESULTS[1]["job"])

    # epoch millis → "YYYY-MM-DD" (Job.posted_at is a string column)
    expected = datetime.fromtimestamp(RESULTS[1]["job"]["datePublished"] / 1000)
    assert item["posted_at"] == expected.strftime("%Y-%m-%d")


def test_strip_html_keeps_text_and_collapses_whitespace():
    assert strip_html("<div><p>Olá&nbsp;  mundo</p><br/><b>!</b></div>") == "Olá mundo !"


# ------------------------------------------------------------------ parse


def test_parse_response_returns_every_result():
    items = parse_response(SEARCH)

    assert len(items) == 25
    assert all(item["source"] == "indeed" for item in items)


def test_parse_response_reads_next_cursor():
    assert parse_response(SEARCH)[0] is not None  # smoke: returns list[dict]

    cursor = SEARCH["data"]["jobSearch"]["pageInfo"]["nextCursor"]
    assert cursor


def test_parse_response_handles_missing_payload():
    assert parse_response({"data": None}) == []
    assert parse_response({"errors": [{"message": "nope"}]}) == []
    assert parse_response({}) == []


# --------------------------------------------------------------------- search


@pytest.mark.asyncio
async def test_search_posts_graphql_with_keyword_and_location():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["headers"] = dict(request.headers)
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json=SEARCH)

    items = await make_source(handler).search("devops", "Curitiba", limit=10)

    assert len(items) == 10  # limit honoured (fixture has 25)
    assert all(item["source"] == "indeed" for item in items)
    assert seen["url"].endswith("/graphql")
    assert 'what: "devops"' in seen["body"]["query"]
    assert 'where: "Curitiba"' in seen["body"]["query"]
    # country + locale headers: without them Indeed answers the wrong market
    assert seen["headers"]["indeed-co"] == "BR"
    assert seen["headers"]["indeed-locale"] == "pt-BR"
    assert seen["headers"]["indeed-api-key"]


@pytest.mark.asyncio
async def test_search_credentials_come_from_settings():
    """Credential and market travel in `.env`, never in code."""
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=SEARCH)

    source = make_source(
        handler,
        indeed_api_key="key-from-env",
        indeed_country="PT",
        indeed_locale="en-PT",
    )
    await source.search("devops", "", limit=1)

    assert seen["headers"]["indeed-api-key"] == "key-from-env"
    assert seen["headers"]["indeed-co"] == "PT"
    assert seen["headers"]["indeed-locale"] == "en-PT"


@pytest.mark.asyncio
async def test_search_refuses_to_fire_without_an_api_key():
    """A missing INDEED_API_KEY is a config error, reported before any call."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not hit Indeed without an api key")

    source = make_source(handler, indeed_api_key="")

    with pytest.raises(SourceUnavailableError, match="INDEED_API_KEY"):
        await source.search("devops", "")


@pytest.mark.asyncio
async def test_search_brazil_omits_the_location_clause():
    queries = []

    def handler(request: httpx.Request) -> httpx.Response:
        queries.append(json.loads(request.content)["query"])
        return httpx.Response(200, json=SEARCH)

    await make_source(handler).search("devops", "Brazil")

    assert "location: {" not in queries[0]


@pytest.mark.asyncio
async def test_search_paginates_by_cursor_until_limit():
    cursors = []

    def handler(request: httpx.Request) -> httpx.Response:
        query = json.loads(request.content)["query"]
        cursors.append("cursor:" in query)
        return httpx.Response(200, json=SEARCH)

    # 25 per page and limit 30 → a second page is required
    source = make_source(handler, indeed_page_size=25)
    items = await source.search("devops", "", limit=30)

    assert len(items) == 30
    assert cursors == [False, True]  # first request has no cursor


@pytest.mark.asyncio
async def test_search_stops_without_a_cursor():
    calls = []
    no_cursor = {"data": {"jobSearch": {"pageInfo": {"nextCursor": None}, "results": RESULTS}}}

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json=no_cursor)

    source = make_source(handler, indeed_page_size=10)
    items = await source.search("devops", "", limit=100)

    assert len(items) == 25
    assert len(calls) == 1  # no cursor = last page


@pytest.mark.asyncio
async def test_search_stops_on_empty_page():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        empty = {"data": {"jobSearch": {"pageInfo": {"nextCursor": "x"}, "results": []}}}
        return httpx.Response(200, json=empty)

    source = make_source(handler, indeed_page_size=10)
    items = await source.search("devops", "", limit=100)

    assert items == []
    assert len(calls) == 1


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


@pytest.mark.asyncio
async def test_search_wraps_graphql_errors_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "auth required"}]})

    with pytest.raises(SourceUnavailableError, match="auth required"):
        await make_source(handler).search("devops", "")


@pytest.mark.asyncio
async def test_search_wraps_non_json_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html>captive portal</html>")

    with pytest.raises(SourceUnavailableError):
        await make_source(handler).search("devops", "")


# ---------------------------------------------------------------------- retry


@pytest.mark.asyncio
async def test_search_retries_transient_failures_then_succeeds(monkeypatch):
    """A blip on the wire must not fail the source: retry with backoff first."""
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 3:
            raise httpx.ConnectError("blip", request=request)
        return httpx.Response(200, json=SEARCH)

    monkeypatch.setattr("app.sources.indeed.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.indeed.random.uniform", lambda low, high: 0.0)

    source = make_source(handler, indeed_max_retries=2, indeed_backoff_seconds=5.0)
    items = await source.search("devops", "", limit=5)

    assert len(items) == 5  # the third attempt delivered
    assert len(calls) == 3  # 1 attempt + 2 retries
    assert slept == [5.0, 10.0]  # 5·2⁰, 5·2¹ (jitter zeroed for the assertion)


@pytest.mark.asyncio
async def test_search_backoff_includes_jitter(monkeypatch):
    """Retry timing must not be deterministic across clients — jitter is added."""
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) < 2:
            raise httpx.ConnectError("blip", request=request)
        return httpx.Response(200, json=SEARCH)

    monkeypatch.setattr("app.sources.indeed.asyncio.sleep", fake_sleep)
    # worst-case jitter = full backoff on top of the exponential base
    monkeypatch.setattr("app.sources.indeed.random.uniform", lambda low, high: high)

    source = make_source(handler, indeed_max_retries=2, indeed_backoff_seconds=5.0)
    await source.search("devops", "", limit=5)

    assert slept == [10.0]  # 5·2⁰ + jitter(5)


@pytest.mark.asyncio
async def test_search_raises_after_exhausting_retries(monkeypatch):
    """After the configured attempts the failure surfaces as unavailable."""
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        raise httpx.ConnectError("down", request=request)

    monkeypatch.setattr("app.sources.indeed.asyncio.sleep", fake_sleep)
    monkeypatch.setattr("app.sources.indeed.random.uniform", lambda low, high: 0.0)

    source = make_source(handler, indeed_max_retries=2, indeed_backoff_seconds=5.0)
    with pytest.raises(SourceUnavailableError, match="request failed"):
        await source.search("devops", "")

    assert len(calls) == 3  # attempts exhausted, then it gives up
    assert slept == [5.0, 10.0]


@pytest.mark.asyncio
async def test_search_does_not_retry_permanent_errors(monkeypatch):
    """GraphQL errors answered the request — retrying cannot change them."""
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, json={"errors": [{"message": "auth required"}]})

    monkeypatch.setattr("app.sources.indeed.asyncio.sleep", fake_sleep)
    source = make_source(handler, indeed_max_retries=3, indeed_backoff_seconds=5.0)

    with pytest.raises(SourceUnavailableError, match="auth required"):
        await source.search("devops", "")

    assert len(calls) == 1
    assert slept == []


@pytest.mark.asyncio
async def test_search_does_not_retry_non_json_responses(monkeypatch):
    """A non-JSON answer (captive portal, HTML shell) is permanent, not transient."""
    calls: list = []
    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return httpx.Response(200, text="<html>captive portal</html>")

    monkeypatch.setattr("app.sources.indeed.asyncio.sleep", fake_sleep)
    source = make_source(handler, indeed_max_retries=3, indeed_backoff_seconds=5.0)

    with pytest.raises(SourceUnavailableError, match="non-JSON"):
        await source.search("devops", "")

    assert len(calls) == 1
    assert slept == []


@pytest.mark.asyncio
async def test_search_applies_configured_delay(monkeypatch):
    slept = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.sources.indeed.asyncio.sleep", fake_sleep)
    source = make_source(lambda request: httpx.Response(200, json=SEARCH), indeed_delay_seconds=1.5)

    await source.search("devops", "")

    assert slept == [1.5]


# --------------------------------------------------------------------- details


@pytest.mark.asyncio
async def test_details_is_a_noop_because_search_carries_the_description():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("details must not fetch: GraphQL already returned it")

    source = make_source(handler)
    item = {"source": "indeed", "source_id": "1", "title": "T", "description": "already"}

    assert await source.details(item) is item
