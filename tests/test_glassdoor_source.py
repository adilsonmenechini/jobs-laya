"""GlassdoorSource — browser-backed via an injectable engine (no real browser).

TDD: written before `app/sources/glassdoor.py` (spec FR-2 / FR-4).
"""

import pytest

from app.config import Settings
from app.sources import SourceUnavailableError
from app.sources.glassdoor import (
    CARDS_SELECTOR,
    HTML_SCRIPT,
    TITLE_SCRIPT,
    GlassdoorSource,
    is_challenge,
    parse_serp,
)
from tests.fixtures_loader import fixture

SERP = fixture("glassdoor_search.html")
SERP_TITLE = "1.318 vaga(s) de Devops – Brasil | Glassdoor"
CHALLENGE_TITLE = "Um momento…"


class FakeEngine:
    """Scripted stand-in for the Patchright engine: records every call."""

    def __init__(self, html: str = SERP, title: str = SERP_TITLE) -> None:
        self.html = html
        self.title = title
        self.visited: list[str] = []
        self.waited: list[str] = []
        self.scripts: list[str] = []
        self.goto_error: Exception | None = None
        self.wait_error: Exception | None = None

    async def goto(self, url: str) -> None:
        if self.goto_error:
            raise self.goto_error
        self.visited.append(url)

    async def wait(self, selector: str) -> None:
        if self.wait_error:
            raise self.wait_error
        self.waited.append(selector)

    async def evaluate(self, script: str) -> str:
        self.scripts.append(script)
        if script == TITLE_SCRIPT:
            return self.title
        if script == HTML_SCRIPT:
            return self.html
        raise AssertionError(f"unexpected script: {script}")


def make_source(engine: FakeEngine, **overrides) -> GlassdoorSource:
    defaults: dict = {
        "glassdoor_base_url": "https://glassdoor.test",
        "glassdoor_delay_seconds": 0.0,
    }
    defaults.update(overrides)
    config = Settings(_env_file=None, **defaults)
    return GlassdoorSource(config, engine=engine)


# ------------------------------------------------------------------ parse (fixture)


def test_parse_serp_reads_every_card_from_the_real_serp():
    items = parse_serp(SERP)

    assert len(items) == 6
    first = items[0]
    assert first["source"] == "glassdoor"
    assert first["source_id"] == "1010249613116"  # jl= param
    assert first["title"] == "DevOps Engineer - Remote Work"
    assert first["company"] == "BairesDev"
    assert first["location"] == "Belo Horizonte, Minas Gerais"
    assert first["remote"] is False  # SERP has no trustworthy badge
    assert first["url"].startswith("https://www.glassdoor.com.br/job-listing/")
    assert "Terraform" in first["description"]
    assert "Habilidades:" in first["description"]
    assert "Jira" in first["description"]
    assert "&hellip;" not in first["description"]  # entities decoded


def test_parse_serp_carries_salary_in_raw():
    items = {item["source_id"]: item for item in parse_serp(SERP)}

    assert "R$" in items["1010279252414"]["raw"]["salary"]
    assert items["1010249613116"]["raw"]["salary"] is None


def test_parse_serp_falls_back_to_path_when_jl_is_missing():
    html = (
        '<li data-test="jobListing"><a data-test="job-title" '
        'href="https://www.glassdoor.com/job-listing/some-role-acme-JV_KO0,9.htm">Some Role</a>'
        '<span class="EmployerProfile_compactEmployerName__x">Acme</span>'
        '<div data-test="emp-location">Curitiba, Paraná</div>'
        '<div data-test="descSnippet"><div>Skill text</div></div></li>'
    )

    [item] = parse_serp(html)

    assert item["source_id"] == "some-role-acme-JV_KO0,9"
    assert item["company"] == "Acme"
    assert item["location"] == "Curitiba, Paraná"
    assert item["description"] == "Skill text"


def test_parse_serp_skips_cards_without_a_title_link():
    html = '<li data-test="jobListing"><div>orphan card</div></li>'

    assert parse_serp(html) == []


# ---------------------------------------------------------------- challenge


def test_is_challenge_detects_cloudflare_interstitial():
    assert is_challenge("Um momento…")
    assert is_challenge("Somente humanos")
    assert is_challenge("Just a moment...")


def test_is_challenge_allows_real_serp_titles():
    assert not is_challenge(SERP_TITLE)


# --------------------------------------------------------------------- search


@pytest.mark.asyncio
async def test_search_navigates_and_returns_parsed_items():
    engine = FakeEngine()
    source = make_source(engine)

    items = await source.search("site reliability", "Curitiba", limit=3)

    assert len(items) == 3
    assert all(item["source"] == "glassdoor" for item in items)
    # one navigation, keyword only — location is documented as ignored
    assert engine.visited == ["https://glassdoor.test/Job/jobs.htm?sc.keyword=site%20reliability"]
    assert engine.waited == [CARDS_SELECTOR]
    assert engine.scripts == [TITLE_SCRIPT, HTML_SCRIPT]


@pytest.mark.asyncio
async def test_search_detects_challenge_before_waiting_for_cards():
    engine = FakeEngine(title=CHALLENGE_TITLE)
    source = make_source(engine)

    with pytest.raises(SourceUnavailableError) as exc:
        await source.search("devops", "")

    assert "challenge" in str(exc.value)
    assert engine.waited == []  # fast fail: no 30s selector timeout


@pytest.mark.asyncio
async def test_search_wraps_navigation_errors():
    engine = FakeEngine()
    engine.goto_error = RuntimeError("browser crashed")
    source = make_source(engine)

    with pytest.raises(SourceUnavailableError):
        await source.search("devops", "")


@pytest.mark.asyncio
async def test_search_wraps_selector_timeout():
    engine = FakeEngine()
    engine.wait_error = TimeoutError("no cards in 30s")
    source = make_source(engine)

    with pytest.raises(SourceUnavailableError):
        await source.search("devops", "")


@pytest.mark.asyncio
async def test_search_applies_configured_delay(monkeypatch):
    slept = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("app.sources.glassdoor.asyncio.sleep", fake_sleep)
    engine = FakeEngine()
    source = make_source(engine, glassdoor_delay_seconds=2.5)

    await source.search("devops", "")

    assert slept == [2.5]


# --------------------------------------------------------------------- details


@pytest.mark.asyncio
async def test_details_returns_the_item_unchanged():
    engine = FakeEngine()
    source = make_source(engine)
    item = {"source": "glassdoor", "source_id": "1", "title": "T", "description": "snippet"}

    result = await source.details(item)

    assert result is item
    assert engine.visited == []  # detail routes are Cloudflare-blocked (spec Non-Goals)


@pytest.mark.asyncio
async def test_details_never_raises_even_with_a_broken_engine():
    engine = FakeEngine()
    engine.goto_error = RuntimeError("browser gone")
    source = make_source(engine)

    assert await source.details({"source": "glassdoor", "source_id": "1"}) == {
        "source": "glassdoor",
        "source_id": "1",
    }
