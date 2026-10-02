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

    raw: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
