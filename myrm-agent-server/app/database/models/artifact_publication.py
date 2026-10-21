"""Artifact publication ORM — per-target publication state.

[POS] Persist latest deploy URL/status per artifact and hosting target.

[INPUT]
- sqlalchemy (POS: Artifact ORM relationship)

[OUTPUT]
- ArtifactPublication model with unique (artifact_id, target_id) constraint
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import relationship

from app.database.models.base import Base


class ArtifactPublication(Base):
    """Publication of an artifact to a specific hosting target."""

    __tablename__ = "artifact_publications"
    __table_args__ = (UniqueConstraint("artifact_id", "hosting_target_id", name="uq_artifact_publication_target"),)

    id = Column(String(36), primary_key=True, index=True)
    artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=False, index=True)
    hosting_target_id = Column(String(36), nullable=False, index=True)
    publication_url = Column(String(512), nullable=True)
    publication_status = Column(String(50), nullable=True)
    publication_project_ref = Column(String(255), nullable=True)
    publication_version_id = Column(String(36), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    artifact = relationship("Artifact", back_populates="publications")
