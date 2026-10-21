"""Skill package revision model.

[INPUT]
- app.database.models.base::Base (POS: declarative base)

[OUTPUT]
- SkillPackageRevision (table skill_package_revisions: SKILL.md plus resource-file snapshot per revision number)

[POS]
Persistence row behind package-level revision history and fail-closed restore.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database.models.base import Base


class SkillPackageRevision(Base):
    """Point-in-time snapshot of a skill package (SKILL.md + resource files)."""

    __tablename__ = "skill_package_revisions"

    revision_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    skill_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False, default="system")

    skill_md: Mapped[str] = mapped_column(Text, nullable=False, default="")
    resource_files: Mapped[dict[str, str | None]] = mapped_column(JSON, nullable=False, default=dict)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        index=True,
    )
