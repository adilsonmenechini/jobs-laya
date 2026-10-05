"""Candidaturas (kanban): criação idempotente e o filtro dos jobs sem card."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Job, KanbanJob

SNAPSHOT_FIELDS = ("title", "company", "location", "url", "remote")


def job_without_kanban_card():
    """Condição: vaga cuja identidade (source, source_id) não tem card.

    `jobs.id` não serve como chave — SQLite recicla o rowid depois de DELETE.
    O `.correlate(Job)` tira `jobs` do FROM interno, deixando o NOT EXISTS
    válido tanto no `SELECT` do list_jobs quanto no `DELETE` do clean.
    """
    inner = (
        select(KanbanJob.id)
        .where(KanbanJob.source == Job.source, KanbanJob.source_id == Job.source_id)
        .correlate(Job)
    )
    return ~inner.exists()


def find_kanban(db: Session, source: str, source_id: str) -> KanbanJob | None:
    return db.scalar(
        select(KanbanJob).where(KanbanJob.source == source, KanbanJob.source_id == source_id)
    )


def create_kanban(db: Session, source: str, source_id: str) -> tuple[KanbanJob, bool]:
    """Cria o card em CHECK; devolve `(linha, já_existia)`.

    O SELECT antes do INSERT não cobre a corrida de duas abas: o INSERT único
    é protegido por `uq_kanban_jobs_source_source_id` e o `IntegrityError`
    faz rollback + re-SELECT da linha que a outra aba criou (nunca 500).
    """
    existing = find_kanban(db, source, source_id)
    if existing is not None:
        return existing, True

    job = db.scalar(select(Job).where(Job.source == source, Job.source_id == source_id))
    card = KanbanJob(source=source, source_id=source_id, status="CHECK")
    if job is not None:
        # snapshot da vaga de origem: o card sobrevive ao clean sem FK
        for field in SNAPSHOT_FIELDS:
            setattr(card, field, getattr(job, field))
    db.add(card)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = find_kanban(db, source, source_id)
        if existing is None:
            raise  # não era a constraint de unicidade: erro real, não mascarar
        return existing, True
    db.refresh(card)
    return card, False
