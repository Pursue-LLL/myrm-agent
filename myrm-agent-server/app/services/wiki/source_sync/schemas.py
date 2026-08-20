"""Pydantic models for wiki source sync configuration and run results.

[OUTPUT]
- WikiSourceSyncConfig / WikiSourceSyncResult / WikiSourceSyncRunSummary schemas

[POS]
Typed contracts for wiki source sync config persistence and run telemetry.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class WikiSourceSyncConfig(BaseModel):
    feishu_enabled: bool = False
    feishu_folder_token: str = Field(default="", max_length=256)
    gmail_enabled: bool = False
    gmail_label: str = Field(default="ReadLater", max_length=128)
    gdrive_enabled: bool = False
    gdrive_folder_id: str = Field(default="root", max_length=256)
    rss_feeds: list[str] = Field(default_factory=list, max_length=32)
    auto_compile: bool = True
    max_items_per_run: int = Field(default=10, ge=1, le=50)
    mirror_integrations_to_wiki: bool = True


class WikiSourceSyncResult(BaseModel):
    source: str
    published: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list)


class WikiSourceSyncSourceState(BaseModel):
    source: str
    published: int = 0
    skipped: int = 0
    failed: int = 0
    errors: list[str] = Field(default_factory=list, max_length=5)


class WikiSourceSyncState(BaseModel):
    last_sync_at: datetime | None = None
    last_errors: list[str] = Field(default_factory=list, max_length=20)
    sources: list[WikiSourceSyncSourceState] = Field(default_factory=list)
    total_published: int = 0
    total_skipped: int = 0
    total_failed: int = 0


class WikiSourceSyncRunSummary(BaseModel):
    results: list[WikiSourceSyncResult] = Field(default_factory=list)
    total_published: int = 0
    total_skipped: int = 0
    total_failed: int = 0

    @property
    def summary_text(self) -> str:
        if self.total_published == 0 and self.total_failed == 0:
            return "[SILENT]"
        parts: list[str] = []
        for item in self.results:
            if item.published or item.failed:
                parts.append(f"{item.source}: +{item.published} skip {item.skipped} fail {item.failed}")
        return "; ".join(parts) if parts else "[SILENT]"
