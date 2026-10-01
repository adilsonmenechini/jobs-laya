"""Parser tests: LinkedIn HTML -> plain dicts. Pure functions, no browser."""

from app.linkedin.scrape import is_authwall, parse_job_cards, parse_job_detail
from tests.fixtures_loader import fixture


def test_parse_job_cards_extracts_ids_titles_and_metadata():
    items = parse_job_cards(fixture("search_cards.html"))

    assert [item["job_id"] for item in items] == ["3987654321", "2211334455"]
    assert items[0]["title"] == "Senior SRE"
    assert items[0]["company"] == "Acme Corp"
    assert items[0]["location"] == "São Paulo, Brazil"
    assert items[0]["posted_at"] == "2026-09-28"
    assert items[0]["url"] == (
        "https://www.linkedin.com/jobs/view/senior-sre-at-acme-3987654321?refId=abc&trackingId=xyz"
    )
    assert items[1]["title"] == "DevOps Engineer"
    assert items[1]["company"] == "Globex"
    assert items[1]["remote"] is True


def test_parse_job_cards_skips_cards_without_a_job_id():
    html = '<li class="base-search-card"><h3 class="base-search-card__title">No link</h3></li>'

    assert parse_job_cards(html) == []


def test_parse_job_detail_extracts_full_payload():
    item = parse_job_detail(fixture("job_detail.html"), "3987654321")

    assert item["job_id"] == "3987654321"
    assert item["title"] == "Senior SRE"
    assert item["company"] == "Acme Corp"
    assert item["location"] == "São Paulo, Brazil"
    assert item["remote"] is True
    assert item["url"] == "https://www.linkedin.com/jobs/view/senior-sre-at-acme-3987654321"
    assert "Kubernetes, Terraform, AWS" in item["description"]
    # description is plain text: untrusted markup must never survive
    assert "<p>" not in item["description"]
    assert "<li>" not in item["description"]


def test_parse_job_detail_parses_current_hashed_markup():
    """Real 2026 markup: hashed classes, pt-BR headings, no canonical/h1."""
    item = parse_job_detail(fixture("job_detail_new.html"), "4449098125")

    assert item["job_id"] == "4449098125"
    assert item["title"] == "Reliability Engineer - Remote Work | REF#300007"
    assert item["company"] == "BairesDev"
    assert item["location"] == "São Paulo, SP (Remoto)"
    assert item["remote"] is True
    assert "Reliability Engineer, you will ensure" in item["description"]
    # no canonical on the new page -> url is constructed
    assert item["url"] == "https://www.linkedin.com/jobs/view/4449098125"
    # markup never survives: untrusted content stays plain text
    assert "<br>" not in item["description"]
    assert "<strong>" not in item["description"]


def test_parse_job_detail_returns_empty_dict_when_page_has_no_job():
    assert parse_job_detail(fixture("authwall.html"), "123") == {}


def test_is_authwall_detects_login_page_and_redirect():
    assert is_authwall("https://www.linkedin.com/login", "<html></html>") is True
    assert (
        is_authwall("https://www.linkedin.com/checkpoint/lg/login-submit", "<html></html>") is True
    )
    assert is_authwall("https://www.linkedin.com/jobs/view/1", fixture("authwall.html")) is True
    assert is_authwall("https://www.linkedin.com/jobs/view/1", "<html>ok</html>") is False


def test_is_authwall_is_not_triggered_by_job_description_mentioning_login():
    html = "<div class='jobs-box__html-content'>We build a login page</div>"

    assert is_authwall("https://www.linkedin.com/jobs/view/1", html) is False
