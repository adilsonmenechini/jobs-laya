"""Legacy schema migration: linkedin_id table → multi-source (source, source_id)."""

from sqlalchemy import create_engine, inspect, text

from app.db import Base, migrate_legacy_jobs

LEGACY_DDL = """
CREATE TABLE jobs (
    id INTEGER NOT NULL PRIMARY KEY,
    linkedin_id VARCHAR(128) NOT NULL UNIQUE,
    title VARCHAR(500) NOT NULL,
    company VARCHAR(500),
    location VARCHAR(500),
    remote BOOLEAN NOT NULL,
    url VARCHAR(2000),
    description TEXT NOT NULL,
    posted_at VARCHAR(100),
    match VARCHAR(20),
    score FLOAT,
    decision JSON,
    reasons JSON,
    gaps JSON,
    raw JSON,
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL
)
"""

# The real data/jobs.db carries named indexes — renaming the table keeps
# their names and they collide with create_all's (regression caught live).
LEGACY_INDEXES = "\n".join(
    f"CREATE INDEX {name} ON jobs ({column});"
    for name, column in (
        ("ix_jobs_title", "title"),
        ("ix_jobs_company", "company"),
        ("ix_jobs_match", "match"),
        ("ix_jobs_score", "score"),
        ("ix_jobs_remote", "remote"),
        ("ix_jobs_linkedin_id", "linkedin_id"),
    )
)

ROW = (
    "INSERT INTO jobs (id, linkedin_id, title, company, remote, description,"
    " created_at, updated_at) VALUES (1, '123', 'Senior SRE', 'Acme', 1,"
    " 'kubernetes terraform', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
)


def make_legacy_db(tmp_path, with_indexes: bool = True):
    engine = create_engine(f"sqlite:///{tmp_path}/legacy.db")
    with engine.begin() as conn:
        conn.exec_driver_sql(LEGACY_DDL)
        if with_indexes:
            for statement in LEGACY_INDEXES.split(";"):
                if statement.strip():
                    conn.exec_driver_sql(statement)
        conn.exec_driver_sql(ROW)
    return engine


def test_migrate_with_named_indexes_does_not_collide(tmp_path):
    """Regression: renamed legacy indexes keep their names in SQLite."""
    engine = make_legacy_db(tmp_path)

    assert migrate_legacy_jobs(engine) is True

    columns = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert "source" in columns
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar() == 1


def test_migrate_detects_legacy_table(tmp_path):
    engine = make_legacy_db(tmp_path)

    assert migrate_legacy_jobs(engine) is True


def test_migrated_rows_are_preserved_as_linkedin_source(tmp_path):
    engine = make_legacy_db(tmp_path)
    migrate_legacy_jobs(engine)

    with engine.connect() as conn:
        row = conn.execute(text("SELECT source, source_id, title, score FROM jobs")).fetchone()

    assert tuple(row) == ("linkedin", "123", "Senior SRE", None)


def test_migrated_table_has_multi_source_schema(tmp_path):
    engine = make_legacy_db(tmp_path)
    migrate_legacy_jobs(engine)

    columns = {c["name"] for c in inspect(engine).get_columns("jobs")}
    assert "source" in columns
    assert "source_id" in columns
    assert "linkedin_id" not in columns


def test_migrated_schema_accepts_same_id_from_two_sources(tmp_path):
    """The old UNIQUE(linkedin_id) must not survive the migration."""
    engine = make_legacy_db(tmp_path)
    migrate_legacy_jobs(engine)

    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO jobs (source, source_id, title, remote, description,"
            " created_at, updated_at) VALUES ('geekhunter', '123', 'SRE', 1,"
            " 'x', '2026-01-01 00:00:00', '2026-01-01 00:00:00')"
        )
        count = conn.execute(text("SELECT count(*) FROM jobs")).scalar()

    assert count == 2


def test_migrate_is_idempotent(tmp_path):
    engine = make_legacy_db(tmp_path)
    migrate_legacy_jobs(engine)

    assert migrate_legacy_jobs(engine) is False
    with engine.connect() as conn:
        assert conn.execute(text("SELECT count(*) FROM jobs")).scalar() == 1


def test_migrate_skips_fresh_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path}/fresh.db")
    Base.metadata.create_all(bind=engine)

    assert migrate_legacy_jobs(engine) is False
