"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] VaultCredential
[POS] 表单凭证金库模型。用于存储加密的表单凭证（密码、TOTP种子）。
"""

from datetime import datetime

from sqlalchemy import DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class VaultCredential(Base):
    """表单凭证金库表 (AES-256-GCM 加密存储)

    存储用户用于浏览器/桌面自动填充的表单凭证。
    密码和 TOTP 种子在数据库中加密存储。
    """

    __tablename__ = "vault_credentials"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    label: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)

    encrypted_password: Mapped[str | None] = mapped_column(Text, nullable=True)
    encrypted_totp_seed: Mapped[str | None] = mapped_column(Text, nullable=True)

    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
