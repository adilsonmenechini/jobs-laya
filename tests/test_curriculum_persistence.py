"""jobs.curriculum_version — stamped at classify time, never rewritten (CA11/CA12).

R8/R9: a classification records WHICH curriculum produced it, and editing the
file afterwards must not touch historical rows. There is no reclassification on
save, so the stamped version is what makes a stale verdict readable later.
"""

import pytest
from sqlalchemy import delete, select

from app.classifier.laya_classifier import LayaInspiredClassifier
from app.db import SessionLocal, engine, init_db
from app.models import Job
from app.services import curriculum
from app.services.jobs import upsert_job

PROFILE = {
    "titles": ["SRE", "DevOps", "Platform Engineer"],
    "seniority": ["Senior", "Staff"],
    "remote_required": True,
    "skills": ["AWS", "Kubernetes", "Terraform", "Prometheus", "Python"],
}

NORMALIZED = {
    "source": "gupy",
    "source_id": "curriculum-test-1",
    "title": "Senior SRE",
    "company": "Acme",
    "location": "Brazil",
    "url": "https://example.test/j/1",
    "remote": True,
    "description": "Senior SRE with AWS Kubernetes Terraform Prometheus Python.",
}

MARKDOWN = "# Candidate\n\n## Skills\n- Kubernetes, Terraform, AWS\n"


@pytest.fixture(autouse=True)
def clean_jobs():
    init_db()
    with SessionLocal() as db:
        db.execute(delete(Job))
        db.commit()
    yield
    with SessionLocal() as db:
        db.execute(delete(Job))
        db.commit()


@pytest.fixture()
def curriculum_file(tmp_path, monkeypatch):
    path = tmp_path / "curriculum.md"
    monkeypatch.setattr(curriculum, "DEFAULT_PATH", str(path))
    return path


def stamp(normalized=None, curriculum_path=None):
    classifier = LayaInspiredClassifier(PROFILE, curriculum_path)
    with SessionLocal() as db:
        return upsert_job(db, dict(normalized or NORMALIZED), classifier)


def read_version(source_id: str = "curriculum-test-1"):
    with SessionLocal() as db:
        job = db.scalar(select(Job).where(Job.source_id == source_id))
        return None if job is None else job.curriculum_version


def test_curriculum_version_is_null_without_a_curriculum(curriculum_file):
    """CA1: a job classified with no résumé records no version."""
    assert not curriculum_file.exists()

    job = stamp()

    assert job.curriculum_version is None


def test_curriculum_version_records_the_content_hash(curriculum_file):
    """CA11: the stamped value is the sha256 the API reports as `version`."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")

    job = stamp()

    assert job.curriculum_version == curriculum.version(curriculum_file)
    assert job.curriculum_version is not None


def test_updating_the_curriculum_does_not_rewrite_a_stored_row(curriculum_file):
    """CA12/R9: editing the file leaves historical classifications alone."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    job = stamp()
    first_version = job.curriculum_version
    first_score = job.score

    curriculum_file.write_text(MARKDOWN + "\n## Mais\n- Go\n", encoding="utf-8")
    assert curriculum.version(curriculum_file) != first_version

    assert read_version() == first_version
    with SessionLocal() as db:
        stored = db.scalar(select(Job).where(Job.source_id == "curriculum-test-1"))
        assert stored.score == first_score


def test_resyncing_the_same_job_stamps_the_new_version(curriculum_file):
    """A new classification records the curriculum that produced it."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    first_version = stamp().curriculum_version

    curriculum_file.write_text(MARKDOWN + "\n## Mais\n- Go\n", encoding="utf-8")
    second_version = stamp().curriculum_version

    assert second_version == curriculum.version(curriculum_file)
    assert second_version != first_version


def test_deleting_the_curriculum_stamps_null_on_the_next_sync(curriculum_file):
    """Removing the file is a supported transition, not an error."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    assert stamp().curriculum_version is not None

    curriculum_file.unlink()
    job = stamp()

    assert job.curriculum_version is None
    assert job.match in {"high", "medium", "low"}


def test_curriculum_version_is_a_sha256_hex_digest(curriculum_file):
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")

    version = stamp().curriculum_version

    assert version is not None
    assert len(version) == 64
    assert set(version) <= set("0123456789abcdef")


def test_two_jobs_classified_under_different_versions_can_be_told_apart(
    curriculum_file,
):
    """The point of the column: a mixed-history table stays auditable."""
    curriculum_file.write_text(MARKDOWN, encoding="utf-8")
    stamp()
    first = read_version()

    curriculum_file.write_text(MARKDOWN + "\nGo e Rust.\n", encoding="utf-8")
    other = {**NORMALIZED, "source_id": "curriculum-test-2"}
    stamp(other)

    assert read_version("curriculum-test-1") == first
    assert read_version("curriculum-test-2") == curriculum.version(curriculum_file)
    assert first != read_version("curriculum-test-2")


def test_column_exists_on_a_fresh_database():
    """create_all builds the table with the column — the migration is the
    add-on path for pre-existing databases."""
    from sqlalchemy import inspect

    columns = {c["name"] for c in inspect(engine).get_columns("jobs")}

    assert "curriculum_version" in columns


def test_migration_adds_the_column_to_a_legacy_table(tmp_path):
    """create_all never alters an existing table: the ALTER TABLE is required."""
    from sqlalchemy import create_engine, inspect, text

    from app.db import migrate_curriculum_version

    legacy = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with legacy.begin() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE jobs (id INTEGER PRIMARY KEY, source VARCHAR(32), source_id VARCHAR(128))"
        )

    assert "curriculum_version" not in {c["name"] for c in inspect(legacy).get_columns("jobs")}
    assert migrate_curriculum_version(legacy) is True
    assert "curriculum_version" in {c["name"] for c in inspect(legacy).get_columns("jobs")}

    # Idempotent: a second run is a no-op.
    assert migrate_curriculum_version(legacy) is False
    with legacy.connect() as conn:
        conn.execute(text("SELECT curriculum_version FROM jobs"))
        assert conn.execute(text("SELECT COUNT(*) FROM jobs")).scalar() == 0
