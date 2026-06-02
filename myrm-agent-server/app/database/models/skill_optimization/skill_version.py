"""Skill Version Model

1. 本文件的 INPUT/OUTPUT/POS 注释
2. 所属文件夹的 _ARCH.md

[INPUT]
- sqlalchemy (POS: Python ORM框架)
- datetime (POS: Python标准库日期时间)
- app.database.models.Base (POS: SQLAlchemy基类)

[OUTPUT]
- SkillVersionModel: Skill版本ORM模型

[POS]
定义skill_versions表的ORM模型，用于记录skill的每个版本，支持版本回滚。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class SkillVersionModel(Base):
    """Skill版本ORM模型

    记录skill的每个版本，支持版本回滚和对比。
    """

    __tablename__ = "skill_versions"

    # 主键：使用复合主键 (skill_id, version) 确保唯一性
    skill_id: Mapped[str] = mapped_column(String(255), primary_key=True, index=True)
    version: Mapped[int] = mapped_column(Integer, primary_key=True)

    # 版本内容
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # 质量评分（JSON存储，允许为空）
    quality_score: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # 创建信息
    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        nullable=False,
        default=datetime.utcnow,
    )
    created_by: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="llm",
    )

    # 关联信息
    optimization_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # 激活状态
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 额外元数据（避免与SQLAlchemy Base.metadata冲突，显式指定列名）
    extra_metadata: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<SkillVersion("
            f"skill_id={self.skill_id!r}, "
            f"version={self.version}, "
            f"is_active={self.is_active}, "
            f"created_by={self.created_by!r}"
            f")>"
        )
