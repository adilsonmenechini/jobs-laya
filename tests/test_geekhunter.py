"""GeekHunter parser tests against local fixtures — no network.

Fixture sources (captured 2026-10-01):
- `geekhunter_search.html` — /pt/vagas?searchTerm=SRE (JSON-LD ItemList + cards)
- `geekhunter_job_detail.html` — one job page (JSON-LD JobPosting + body)
"""

import pytest

from app.sources.geekhunter import (
    normalize_modality,
    parse_job_detail,
    parse_search_page,
)
from tests.fixtures_loader import fixture

# `identifier.value` of the fixture's JobPosting JSON-LD: GeekHunter's internal
# id — stable across slug renames, unlike the URL-derived ones.
IDENTIFIER = "5a60a71c44bc345ec59d8f6900b2a91de5dbce415cc4d0d58ffd192d095ae420"
SRE_PATH = "/pt/ntt-data/jobs/site-reliability-engineer--sre--3"


def test_search_extracts_item_list():
    items = parse_search_page(fixture("geekhunter_search.html"))

    assert len(items) == 17
    sre = items[0]
    assert sre["source"] == "geekhunter"
    assert sre["source_id"] == SRE_PATH
    assert sre["title"] == "Analista - Site Reliability Engineer (SRE)"
    assert sre["url"] == (
        "https://www.geekhunter.com/pt/ntt-data/jobs/site-reliability-engineer--sre--3"
    )
    assert sre["company_slug"] == "ntt-data"
    assert sre["remote"] is True  # card badge: "Remoto"
    assert sre["raw"]


def test_search_cards_parse_modality_location_and_excerpt():
    items = parse_search_page(fixture("geekhunter_search.html"))
    by_id = {item["source_id"]: item for item in items}

    remote_job = by_id[SRE_PATH]
    assert remote_job["remote"] is True
    assert remote_job["modality"] == "Remoto"
    assert "Site Reliability Engineer" in remote_job["description"]

    hybrid = by_id["/pt/nava-technology-for-business-1/jobs/sre-senior-32"]
    assert hybrid["remote"] is False
    assert hybrid["modality"] == "Híbrido"
    assert hybrid["location"] == "São Paulo, SP, Brasil"
    assert hybrid["posted_at"] == "Publicada há 5 dias"
    assert "SRE" in hybrid["skills"]


def test_search_source_id_is_the_full_url_path():
    items = parse_search_page(fixture("geekhunter_search.html"))
    for item in items:
        assert item["source_id"].startswith("/pt/")
        assert item["url"].endswith(item["source_id"])
        assert "/jobs/" in item["url"]


def test_search_isolates_equal_slugs_from_different_companies():
    """Two companies sharing a slug must never share a source_id.

    The slug alone collides (its `-N` suffix counts per company), which made
    `parse_search_page` overwrite one job with the other.
    """
    html = """
    <html><body>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"ItemList","itemListElement":[
      {"@type":"ListItem","position":1,"name":"DevOps A",
       "url":"https://www.geekhunter.com/pt/empresa-a/jobs/devops-1"},
      {"@type":"ListItem","position":2,"name":"DevOps B",
       "url":"https://www.geekhunter.com/pt/empresa-b/jobs/devops-1"}
    ]}
    </script></body></html>
    """
    items = parse_search_page(html)

    assert len(items) == 2
    assert {item["source_id"] for item in items} == {
        "/pt/empresa-a/jobs/devops-1",
        "/pt/empresa-b/jobs/devops-1",
    }


def test_search_company_slug_from_url():
    items = parse_search_page(fixture("geekhunter_search.html"))
    by_id = {item["source_id"]: item for item in items}

    hybrid_path = "/pt/nava-technology-for-business-1/jobs/sre-senior-32"
    assert by_id[hybrid_path]["company_slug"] == "nava-technology-for-business-1"


def test_search_empty_html_returns_no_items():
    assert parse_search_page("<html><body>no jobs</body></html>") == []


def test_detail_parses_job_posting_json_ld():
    detail = parse_job_detail(fixture("geekhunter_job_detail.html"))

    assert detail["source"] == "geekhunter"
    assert detail["title"] == "Analista - Site Reliability Engineer (SRE)"
    assert detail["company"] == "NTT DATA"
    assert detail["url"] == (
        "https://www.geekhunter.com/pt/ntt-data/jobs/site-reliability-engineer--sre--3"
    )
    assert detail["source_id"] == IDENTIFIER  # stable internal id, not the slug
    assert detail["posted_at"] == "2026-09-30"
    assert detail["remote"] is True  # jobLocationType: TELECOMMUTE
    assert "dynatrace" in detail["description"]
    assert "Kubernetes" in detail["description"]
    assert "Observabilidade" in detail["skills"]


def test_detail_description_is_text_not_html():
    detail = parse_job_detail(fixture("geekhunter_job_detail.html"))

    assert "<" not in detail["description"]
    assert "4+ anos de experiência na carreira" in detail["description"]


def test_detail_falls_back_to_the_path_without_identifier():
    html = """
    <html><body><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting",
     "url":"https://www.geekhunter.com/pt/acme/jobs/devops-pleno-1",
     "title":"DevOps Pleno","description":"<p>Docker</p>"}
    </script></body></html>
    """
    detail = parse_job_detail(html)

    assert detail["source_id"] == "/pt/acme/jobs/devops-pleno-1"


def test_detail_without_url_or_identifier_does_not_raise():
    html = """
    <html><body><script type="application/ld+json">
    {"@context":"https://schema.org","@type":"JobPosting",
     "title":"DevOps Pleno","description":"<p>Docker</p>"}
    </script></body></html>
    """
    detail = parse_job_detail(html)

    assert detail["source_id"] == ""  # no path to derive from, no crash


def test_detail_without_json_ld_falls_back_to_body():
    html = """
    <html><body>
      <h1>DevOps Pleno</h1>
      <p>Remoto</p>
      <div id="job-details"><h2>Requisitos</h2>
        <span>Docker</span><span>Kubernetes</span>
      </div>
    </body></html>
    """
    detail = parse_job_detail(html)

    assert detail["title"] == "DevOps Pleno"
    assert detail["remote"] is True
    assert "Docker" in detail["description"]


def test_detail_missing_everything_raises():
    with pytest.raises(KeyError):
        parse_job_detail("<html><body>nothing here</body></html>")


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        ("Remoto", True),
        ("Híbrido", False),
        ("Presencial", False),
        ("", False),
        (None, False),
    ],
)
def test_normalize_modality(label, expected):
    assert normalize_modality(label) is expected
