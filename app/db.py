from collections.abc import Generator

from sqlalchemy import (
    MetaData,
    Table,
    create_engine,
    insert,
    inspect,
    literal,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.schema import DropIndex

from app.config import ensure_data_dir, settings

ensure_data_dir()

connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
engine = create_engine(settings.database_url, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _legacy_jobs_columns(db_engine: Engine) -> set[str] | None:
    """Columns of a pre-multi-source `jobs` table, or None when not legacy."""
    inspector = inspect(db_engine)
    if "jobs" not in inspector.get_table_names():
        return None
    columns = {column["name"] for column in inspector.get_columns("jobs")}
    if "linkedin_id" in columns and "source" not in columns:
        return columns
    return None


def migrate_legacy_jobs(db_engine: Engine) -> bool:
    """Rebuild a legacy `jobs` table into the multi-source schema.

    The old table had `linkedin_id UNIQUE`, which would reject the same id
    from a second provider — so renaming alone is not enough. SQLite cannot
    drop a constraint: rename the table, let metadata create the new one,
    copy rows over (as `source='linkedin'`) and drop the legacy table.
    Returns True when a migration ran.
    """
    if not _legacy_jobs_columns(db_engine):
        return False

    with db_engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE jobs RENAME TO jobs_legacy")

    # SQLite keeps index names on rename: they would collide with the ones
    # create_all generates for the new table (ix_jobs_title, …). Reflecting
    # the table gives DropIndex objects — identifiers never hit string SQL.
    legacy_ref = Table("jobs_legacy", MetaData(), autoload_with=db_engine)
    named_indexes = [
        index
        for index in legacy_ref.indexes
        if index.name and not index.name.startswith("sqlite_autoindex")
    ]

    with db_engine.begin() as conn:
        for index in sorted(named_indexes, key=lambda i: i.name or ""):
            conn.execute(DropIndex(index))

    import app.models  # noqa: F401  # populate metadata before create

    Base.metadata.create_all(bind=db_engine)

    from app.models import Job

    with db_engine.connect() as conn:
        new_columns = {column["name"] for column in inspect(conn).get_columns("jobs")}
    legacy_columns = {column.name for column in legacy_ref.columns}
    copied = sorted((new_columns - {"source", "source_id"}) & legacy_columns)

    # Core insert().from_select(): compiled identifiers, no string SQL.
    statement = insert(Job.__table__).from_select(
        ["source", "source_id", *copied],
        select(
            literal("linkedin"),
            legacy_ref.c.linkedin_id,
            *[legacy_ref.c[name] for name in copied],
        ),
    )
    with db_engine.begin() as conn:
        conn.execute(statement)
        conn.exec_driver_sql("DROP TABLE jobs_legacy")
    return True


def init_db() -> None:
    from app.models import Job, KanbanJob  # noqa: F401

    migrate_legacy_jobs(engine)
    Base.metadata.create_all(bind=engine)
