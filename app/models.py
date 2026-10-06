from datetime import UTC, datetime

from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Job(Base):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_jobs_source_source_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), default="linkedin", index=True)
    source_id: Mapped[str] = mapped_column(String(128), index=True)
    title: Mapped[str] = mapped_column(String(500), index=True)
    company: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    remote: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    description: Mapped[str] = mapped_column(Text, default="")
    posted_at: Mapped[str | None] = mapped_column(String(100), nullable=True)

    match: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    decision: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reasons: Mapped[list | None] = mapped_column(JSON, nullable=True)
    gaps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # sha256 of data/curriculum.md at classify time (SPEC 202610051432, R8):
    # stamping happens where the verdict is written; NULL when there was no
    # curriculum. Editing the file never rewrites historical rows (R9).
    curriculum_version: Mapped[str | None] = mapped_column(String(64), nullable=True)

    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )


class KanbanJob(Base):
    """A candidatura, identificada por (source, source_id) — nunca por jobs.id.

    SQLite recicla o rowid depois de DELETE: ligar a candidatura a `jobs.id`
    faria o card apontar para outra vaga após um clean + recoleção. Sem FK para
    `jobs`: o snapshot (title/company/location/url/remote) mantém o card fiel
    mesmo quando a linha de origem some.
    """

    __tablename__ = "kanban_jobs"
    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_kanban_jobs_source_source_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)
    source_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    company: Mapped[str | None] = mapped_column(String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(String(500), nullable=True)
    url: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    remote: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="CHECK", nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    applied_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
