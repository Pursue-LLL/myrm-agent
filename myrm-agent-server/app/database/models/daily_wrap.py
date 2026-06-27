"""Daily Wrap cache model.

[INPUT]
- app.database.models.base::Base (POS: SQLAlchemy Base model)

[OUTPUT]
- DailyWrapCache: class — Cached AI-generated daily wrap summary (one row per date).

[POS]
Stores AI-generated daily activity summaries to avoid redundant LLM calls.
Each row represents one day's cached wrap (summary, keywords, suggestions).
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.database.models.base import Base


class DailyWrapCache(Base):
    """Cached AI-generated daily wrap summary. One row per date."""

    __tablename__ = "daily_wrap_cache"

    date = Column(String(10), primary_key=True, nullable=False)
    summary = Column(Text, nullable=False)
    keywords = Column(Text, nullable=False, default="[]")
    suggestions = Column(Text, nullable=False, default="[]")
    generated_at = Column(DateTime, nullable=False)
