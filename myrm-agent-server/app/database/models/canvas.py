"""Canvas model.

[INPUT]
- app.database.models.base::Base (POS: SQLAlchemy Base model)

[OUTPUT]
- Canvas: class — Infinite canvas workspace metadata.

[POS]
Stores canvas metadata (name, associations, thumbnail) while the full
tldraw snapshot JSON lives on the filesystem under ~/.myrm/canvas/.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, String, Text

from app.database.models.base import Base


class Canvas(Base):
    """Infinite canvas workspace metadata."""

    __tablename__ = "canvas"

    id = Column(String(36), primary_key=True, nullable=False)
    name = Column(String(256), nullable=False, default="Untitled Canvas")
    agent_id = Column(String(36), nullable=True)
    chat_id = Column(String(36), nullable=True)
    thumbnail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
