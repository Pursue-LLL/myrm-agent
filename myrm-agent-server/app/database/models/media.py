"""
[INPUT] models.base::Base (POS: ORM 模型基类)
[OUTPUT] MediaLibrary: 媒体图库
[POS] 媒体域模型。管理 AI 生成的媒体资源元数据。
"""

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base


class MediaLibrary(Base):
    """媒体图库表

    存储 AI 生成的所有图片/视频/音频的元数据。
    实际文件通过 StorageProvider 存储。
    """

    __tablename__ = "media_library"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)

    media_type: Mapped[str] = mapped_column(String(20), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="generate")
    prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    resolution: Mapped[str | None] = mapped_column(String(32), nullable=True)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False, default="image/png")
    file_size: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    storage_key: Mapped[str] = mapped_column(String(500), nullable=False)
    thumbnail_key: Mapped[str | None] = mapped_column(String(500), nullable=True)

    tags: Mapped[list[str] | None] = mapped_column(JSON, nullable=True, default=list)

    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
