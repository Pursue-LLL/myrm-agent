"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] FaqCorpus, FaqEntry, FaqHitLog: FAQ 语义缓存域模型
[POS] Channel FAQ 语义缓存持久化模型。per-agent FAQ 语料库、Q&A 条目及命中记录。
"""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base


class FaqCorpus(Base):
    """Per-agent FAQ corpus with match threshold and enable switch."""

    __tablename__ = "faq_corpus"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    enabled: Mapped[bool] = mapped_column(default=True, nullable=False)
    threshold: Mapped[float] = mapped_column(Float, default=0.85, nullable=False)
    min_score_gap: Mapped[float] = mapped_column(Float, default=0.15, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    entries: Mapped[list["FaqEntry"]] = relationship(
        back_populates="corpus",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class FaqEntry(Base):
    """Single Q&A pair within a FAQ corpus."""

    __tablename__ = "faq_entries"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    corpus_id: Mapped[str] = mapped_column(
        String(32),
        ForeignKey("faq_corpus.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    corpus: Mapped["FaqCorpus"] = relationship(back_populates="entries")


class FaqHitLog(Base):
    """Records each FAQ match attempt for analytics."""

    __tablename__ = "faq_hit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corpus_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entry_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False)
    user_query: Mapped[str] = mapped_column(Text, nullable=False)
    top_score: Mapped[float] = mapped_column(Float, nullable=False)
    hit: Mapped[bool] = mapped_column(default=False, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_faq_hit_logs_corpus_hit", "corpus_id", "hit"),
    )
