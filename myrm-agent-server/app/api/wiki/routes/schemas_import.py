"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- ImportFolderRequest: ImportFolderRequest
- ImportResultResponse: ImportResultResponse
- ImportUrlsRequest: ImportUrlsRequest
- UrlImportErrorCode: UrlImportErrorCode
- UrlImportItemResult: UrlImportItemResult
- ImportUrlsResultResponse: ImportUrlsResultResponse
- ImportVideoRequest: ImportVideoRequest
- ImportVideoResponse: ImportVideoResponse
- ObsidianImportRequest: ObsidianImportRequest
- ObsidianImportResultResponse: ObsidianImportResultResponse

[POS]
Wiki API 的子路由模块；由 app/api/wiki/router.py 组装到 /wiki 前缀下。
"""

import logging
from typing import TYPE_CHECKING, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

router = APIRouter(tags=["wiki"])


class ImportFolderRequest(BaseModel):
    folder_path: str = Field(..., min_length=1, description="Absolute path to local folder")
    extensions: list[str] = Field(
        default=[".md", ".txt", ".org"],
        description="File extensions to include",
    )
    auto_compile: bool = Field(default=True, description="Start compilation after import")
    on_conflict: Literal["skip", "supersede"] = Field(
        default="skip",
        description="When a raw file already exists with different content",
    )
    supersede_reason: str = Field(default="", description="Required when on_conflict is supersede")


class ImportResultResponse(BaseModel):
    success: bool
    files_scanned: int
    files_enqueued: int
    files_skipped_conflict: int = 0
    files_superseded: int = 0
    files_security_blocked: int = 0
    files_security_redacted: int = 0
    conflict_paths: list[str] = Field(default_factory=list)
    security_blocked_paths: list[str] = Field(default_factory=list)
    security_redacted_paths: list[str] = Field(default_factory=list)
    message: str


class ImportUrlsRequest(BaseModel):
    urls: list[str] = Field(
        ...,
        min_length=1,
        max_length=50,
        description="List of web URLs to import into the wiki (max 50)",
    )
    folder_path: str = Field(
        default="",
        description="Optional logical folder path to categorize imported documents (e.g. 'Articles/Tech')",
    )
    auto_compile: bool = Field(
        default=True,
        description="Start compilation after import",
    )
    on_conflict: Literal["skip", "supersede"] = Field(
        default="skip",
        description="When a raw file already exists with different content",
    )
    supersede_reason: str = Field(
        default="",
        description="Required when on_conflict is supersede",
    )


# Why a web page or video URL failed to import. Each import dialog renders its own localized sentence per code.
UrlImportErrorCode = Literal["address_rejected", "nothing_readable", "import_failed"]


class UrlImportItemResult(BaseModel):
    url: str
    relative_path: str = ""
    status: Literal[
        "success",
        "skipped_conflict",
        "superseded",
        "security_blocked",
        "security_redacted",
        "error",
    ]
    # English diagnostic for API clients; the import dialog shows the localized text of `error_code` instead.
    error: str = ""
    error_code: UrlImportErrorCode | None = None


class ImportUrlsResultResponse(BaseModel):
    success: bool
    total_urls: int
    processed_count: int
    enqueued_count: int
    skipped_conflict_count: int = 0
    superseded_count: int = 0
    security_blocked_count: int = 0
    security_redacted_count: int = 0
    error_count: int = 0
    results: list[UrlImportItemResult] = Field(default_factory=list)
    message: str


class ImportVideoRequest(BaseModel):
    url: str = Field(
        ...,
        min_length=1,
        description="Online video URL (e.g. Bilibili, YouTube)",
    )
    folder_path: str = Field(
        default="videos",
        description="Logical folder path in wiki raw folder (e.g. 'videos' or 'lectures')",
    )
    preferred_languages: list[str] = Field(
        default=["zh-Hans", "zh-CN", "zh", "en"],
        description="Preferred transcript languages in priority order",
    )
    window_duration_seconds: int = Field(
        default=45,
        ge=10,
        le=300,
        description="Semantic merge sliding window duration in seconds",
    )
    auto_compile: bool = Field(
        default=True,
        description="Start compilation after import",
    )
    on_conflict: Literal["skip", "supersede"] = Field(
        default="skip",
        description="When a raw file already exists with different content",
    )
    supersede_reason: str = Field(
        default="",
        description="Required when on_conflict is supersede",
    )


class ImportVideoResponse(BaseModel):
    success: bool
    url: str
    relative_path: str = ""
    status: Literal["success", "skipped_conflict", "superseded", "security_blocked", "error"]
    # English diagnostic for API clients; the video dialog shows the localized text of `error_code` instead.
    error: str = ""
    error_code: UrlImportErrorCode | None = None
    message: str


class ObsidianImportRequest(BaseModel):
    vault_path: str = Field(..., min_length=1, description="Absolute path to Obsidian vault folder")
    auto_compile: bool = Field(default=True, description="Start compilation after import")
    on_conflict: Literal["skip", "supersede"] = Field(default="skip")
    supersede_reason: str = Field(default="")


class ObsidianImportResultResponse(BaseModel):
    success: bool
    files_scanned: int
    files_processed: int
    files_enqueued: int
    files_skipped: int
    files_skipped_conflict: int = 0
    files_superseded: int = 0
    files_security_blocked: int = 0
    files_security_redacted: int = 0
    conflict_paths: list[str] = Field(default_factory=list)
    security_blocked_paths: list[str] = Field(default_factory=list)
    security_redacted_paths: list[str] = Field(default_factory=list)
    tags_extracted: int
    images_copied: int
    message: str
