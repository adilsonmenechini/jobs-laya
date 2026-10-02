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


def test_search_extracts_item_list():
    items = parse_search_page(fixture("geekhunter_search.html"))

    assert len(items) == 17
    sre = items[0]
    assert sre["source"] == "geekhunter"
    assert sre["source_id"] == "site-reliability-engineer--sre--3"
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

    remote_job = by_id["site-reliability-engineer--sre--3"]
    assert remote_job["remote"] is True
    assert remote_job["modality"] == "Remoto"
    assert "Site Reliability Engineer" in remote_job["description"]

    hybrid = by_id["sre-senior-32"]
    assert hybrid["remote"] is False
    assert hybrid["modality"] == "Híbrido"
    assert hybrid["location"] == "São Paulo, SP, Brasil"
    assert hybrid["posted_at"] == "Publicada há 5 dias"
    assert "SRE" in hybrid["skills"]


def test_search_source_id_comes_from_url_slug():
    items = parse_search_page(fixture("geekhunter_search.html"))
    for item in items:
        assert item["source_id"]
        assert item["url"].endswith(item["source_id"])
        assert "/jobs/" in item["url"]


def test_search_company_slug_from_url():
    items = parse_search_page(fixture("geekhunter_search.html"))
    by_id = {item["source_id"]: item for item in items}

    assert by_id["sre-senior-32"]["company_slug"] == "nava-technology-for-business-1"


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
    assert detail["source_id"] == "site-reliability-engineer--sre--3"
    assert detail["posted_at"] == "2026-09-30"
    assert detail["remote"] is True  # jobLocationType: TELECOMMUTE
    assert "dynatrace" in detail["description"]
    assert "Kubernetes" in detail["description"]
    assert "Observabilidade" in detail["skills"]


def test_detail_description_is_text_not_html():
    detail = parse_job_detail(fixture("geekhunter_job_detail.html"))

    assert "<" not in detail["description"]
    assert "4+ anos de experiência na carreira" in detail["description"]


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
