"""Widget KV Storage model.

[INPUT]
- app.database.models.base::Base (POS: SQLAlchemy Base model)

[OUTPUT]
- WidgetKVEntry: class — Per-namespace key-value storage for sandboxed widget iframes.

[POS]
Provides persistent key-value storage for AI-generated HTML widgets rendered
in sandboxed iframes. Widgets cannot access localStorage due to iframe sandbox
policy (allow-scripts without allow-same-origin), so this table backs a
postMessage-based storage bridge.
"""

from datetime import datetime

from sqlalchemy import Column, DateTime, Index, String, Text

from app.database.models.base import Base


class WidgetKVEntry(Base):
    """Per-widget namespace key-value entry."""

    __tablename__ = "widget_kv"
    __table_args__ = (
        Index("ix_widget_kv_chat_id", "chat_id"),
        Index("ix_widget_kv_namespace_key", "namespace", "key", unique=True),
    )

    namespace = Column(String(128), primary_key=True, nullable=False)
    key = Column(String(256), primary_key=True, nullable=False)
    value = Column(Text, nullable=False)
    chat_id = Column(String(36), nullable=False, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
