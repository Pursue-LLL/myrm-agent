"""Batch Audit Log Model

SQLAlchemy model for batch optimization audit logs.
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class BatchAuditLog(Base):
    """批量优化审计日志表

    记录批量优化的所有关键操作和事件，用于审计追踪。

    Fields:
        log_id: Unique log identifier
        batch_id: Associated batch task ID
        user_id: User who performed the operation
        operation: Operation type (create/start/complete/cancel/rollback)
        status: Operation status (success/failure)
        details: Operation details (JSON)
        error_message: Error message if operation failed
        ip_address: Client IP address (optional)
        user_agent: Client user agent (optional)
        created_at: Log creation timestamp
    """

    __tablename__ = "batch_audit_logs"

    log_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    batch_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    operation: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)

    details: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(255), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
