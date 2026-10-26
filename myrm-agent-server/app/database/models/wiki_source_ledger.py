"""
[INPUT] models.base::Base (POS: ORM base model)
[OUTPUT] WikiSourceLedgerEntry: per-item import ledger for external wiki sources
[POS] One row per remote item a connector has inventoried, carrying its remote version, import status and
      fidelity so a resumable backfill, remote-deletion detection and an honest import report need no rescan.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class WikiSourceLedgerEntry(Base):
    """Import state of one remote item (``source`` names the connector, e.g. ``ima``)."""

    __tablename__ = "wiki_source_ledger"
    __table_args__ = (
        Index("ix_wiki_source_ledger_status", "agent_scope", "source", "status"),
        Index("ix_wiki_source_ledger_container", "agent_scope", "source", "container_id"),
    )

    agent_scope: Mapped[str] = mapped_column(String(128), primary_key=True)
    source: Mapped[str] = mapped_column(String(16), primary_key=True)
    item_key: Mapped[str] = mapped_column(String(64), primary_key=True)

    container_id: Mapped[str] = mapped_column(String(128), nullable=False)
    container_name: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    remote_id: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    title: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    folder_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    media_type: Mapped[int | None] = mapped_column(Integer, nullable=True)

    remote_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    synced_version: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    fidelity: Mapped[str] = mapped_column(String(8), nullable=False, default="")
    fidelity_notes: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    raw_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    char_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_kind: Mapped[str] = mapped_column(String(24), nullable=False, default="")
    seen_generation: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
