"""
[POS] Fission 任务拓扑图状态模型。用于持久化高并发子代理执行图，防浏览器刷新状态丢失。
"""

from datetime import datetime

from sqlalchemy import (
    JSON,
    DateTime,
    Float,
    String,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class FissionTaskRecord(Base):
    """Fission任务记录表 (Agent Work Map Backend)"""

    __tablename__ = "fission_task_records"

    fission_id: Mapped[str] = mapped_column(String(255), primary_key=True)

    chat_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    agent_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    nodes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
