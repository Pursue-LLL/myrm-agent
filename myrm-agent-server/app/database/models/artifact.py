"""Artifact models for Enterprise Collaborative Vault.

[INPUT]
- app.database.models.base::Base (POS: SQLAlchemy Base model)

[OUTPUT]
- Artifact: class — Logical artifact grouping
- ArtifactVersion: class — Immutable snapshot of an artifact
- ArtifactAuditLog: class — Audit trail for artifact operations

[POS]
Provides enterprise artifact models with tamper-evident tracking.
"""

from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.database.models.base import Base


class Artifact(Base):
    """Logical grouping of an artifact across multiple versions."""

    __tablename__ = "artifacts"

    id = Column(String(36), primary_key=True, index=True)
    tenant_id = Column(String(36), index=True, nullable=True)  # For SaaS isolation
    owner_id = Column(String(36), index=True, nullable=True)  # User ID
    chat_id = Column(String(36), index=True, nullable=True)  # Optional association
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    is_deleted = Column(Boolean, default=False, nullable=False)  # Soft delete
    deployment_url = Column(String(512), nullable=True)  # Public URL after deployment
    deployment_project_id = Column(String(255), nullable=True)  # Vercel project ID
    deployment_status = Column(String(50), nullable=True)  # e.g., DEPLOYING, READY, ERROR
    deployment_version_id = Column(String(36), nullable=True)  # Version ID last deployed
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    versions = relationship("ArtifactVersion", back_populates="artifact", cascade="all, delete-orphan")
    audit_logs = relationship("ArtifactAuditLog", back_populates="artifact", cascade="all, delete-orphan")


class ArtifactVersion(Base):
    """Immutable snapshot of an artifact."""

    __tablename__ = "artifact_versions"

    id = Column(String(36), primary_key=True, index=True)
    artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=False, index=True)
    vault_uri = Column(String(255), nullable=False, unique=True)  # e.g., vault://uuid
    sha256_hash = Column(String(64), nullable=False)  # Tamper-evident hash
    creator_id = Column(String(36), nullable=True)  # User or Agent ID
    commit_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    artifact = relationship("Artifact", back_populates="versions")


class ArtifactAuditLog(Base):
    """Audit trail for artifact operations."""

    __tablename__ = "artifact_audit_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    artifact_id = Column(String(36), ForeignKey("artifacts.id"), nullable=False, index=True)
    user_id = Column(String(36), nullable=True, index=True)
    action = Column(String(50), nullable=False)  # e.g., "CREATE", "READ", "UPDATE", "SOFT_DELETE"
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)

    artifact = relationship("Artifact", back_populates="audit_logs")
