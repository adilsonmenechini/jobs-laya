"""Tests for the payload-merging rules that protect sync from failed parses."""

from app.linkedin.parsing import extract_job_items, merge_job_details, normalize_job


def test_merge_keeps_search_data_when_detail_is_empty():
    search = normalize_job(
        {"job_id": "123", "title": "Senior SRE", "company": "Acme", "location": "Brazil"}
    )
    original = dict(search)

    assert merge_job_details(search, {}) is search
    assert merge_job_details(search, None) is search
    assert search == original
    assert search["linkedin_id"] == "123"


def test_merge_applies_a_valid_detail():
    search = normalize_job({"job_id": "123", "title": "Senior SRE"})
    details = {
        "job": {
            "job_id": "123",
            "title": "Senior SRE - Global",
            "company": "Acme",
            "description": "Own reliability.",
            "remote": True,
        }
    }

    merge_job_details(search, details)

    assert search["title"] == "Senior SRE - Global"
    assert search["company"] == "Acme"
    assert search["description"] == "Own reliability."
    assert search["remote"] is True
    assert search["linkedin_id"] == "123"


def test_merge_never_downgrades_remote_true():
    search = normalize_job({"job_id": "1", "title": "SRE", "remote": True})
    details = {"job_id": "1", "title": "SRE", "description": "text", "remote": False}

    merge_job_details(search, details)

    assert search["remote"] is True


def test_merge_still_reads_remote_upgrade_from_detail():
    search = normalize_job({"job_id": "1", "title": "SRE"})
    details = {"job_id": "1", "title": "SRE", "description": "text", "remote": True}

    merge_job_details(search, details)

    assert search["remote"] is True


def test_extract_then_merge_roundtrip():
    items = extract_job_items({"jobs": [{"job_id": "9", "title": "Platform Engineer"}]})
    merged = merge_job_details(items[0], {})

    assert merged["linkedin_id"] == "9"
    assert merged["title"] == "Platform Engineer"
