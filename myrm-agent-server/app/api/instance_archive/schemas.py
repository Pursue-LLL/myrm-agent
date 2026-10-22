"""Instance archive API schemas.

[INPUT]
- pydantic: request / response validation

[OUTPUT]
- Export / import / outcome request and response models
- Scheduled backup settings request and state response

[POS]
Wire contracts of the instance backup endpoints. Machine-readable ``code`` /
``reentry`` identifiers cross the wire; all user-facing wording lives in the
frontend locale files.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from app.services.instance_archive.auto_backup import DEFAULT_KEEP, KEEP_MAX, KEEP_MIN

RestartMode = Literal["sandbox", "process"]


class ArchiveStatusResponse(BaseModel):
    supported: bool
    can_protect_secrets: bool
    restart_mode: RestartMode
    pending_operation: str | None
    rollback_available: bool


class StartExportRequest(BaseModel):
    passphrase: str | None = Field(default=None, min_length=8, max_length=256)


class ExportJobResponse(BaseModel):
    job_id: str
    state: str
    files_done: int = 0
    files_total: int = 0
    bytes_done: int = 0
    bytes_total: int = 0
    size_bytes: int | None = None
    error_code: str | None = None
    reentry: list[str] = Field(default_factory=list)
    config_key_carried: bool = False
    unreadable_count: int = 0


class CreateUploadRequest(BaseModel):
    size_bytes: int = Field(gt=0)
    chunk_bytes: int = Field(gt=0)


class UploadSessionResponse(BaseModel):
    session_id: str
    size_bytes: int
    chunk_bytes: int
    chunk_count: int
    received: list[int]
    state: str
    report: dict[str, object] | None = None


class StageImportRequest(BaseModel):
    passphrase: str | None = Field(default=None, max_length=256)
    skip_secrets: bool = False


class ConfirmImportRequest(BaseModel):
    acknowledge_executables: bool = False


class QueuedSwapResponse(BaseModel):
    operation: str
    requires_restart: bool = True


class OutcomeResponse(BaseModel):
    operation: str
    status: str
    completed_at: str
    summary: dict[str, int]
    reentry: list[str]
    error_code: str | None
    rollback_available: bool


class OutcomeEnvelope(BaseModel):
    """``outcome`` is null when no swap result is waiting to be shown (JSON ``null`` bodies break the shared client)."""

    outcome: OutcomeResponse | None = None


BackupFrequency = Literal["daily", "weekly"]


class AutoBackupSettingsRequest(BaseModel):
    enabled: bool
    frequency: BackupFrequency
    keep: int = Field(ge=KEEP_MIN, le=KEEP_MAX)
    directory: str | None = Field(default=None, max_length=1024)

    @field_validator("directory")
    @classmethod
    def _blank_means_default(cls, value: str | None) -> str | None:
        if value and "\x00" in value:
            raise ValueError("The backup folder path contains an invalid character")
        return (value or "").strip() or None


class BackupFileResponse(BaseModel):
    name: str
    created_at: str
    size_bytes: int


class AutoBackupResponse(BaseModel):
    supported: bool
    enabled: bool = False
    frequency: BackupFrequency = "daily"
    keep: int = DEFAULT_KEEP
    directory: str = ""
    default_directory: bool = True
    folder_available: bool = True
    running: bool = False
    overdue: bool = False
    last_success_at: str | None = None
    last_success_size: int | None = None
    consecutive_failures: int = 0
    last_error_code: str | None = None
    backups: list[BackupFileResponse] = Field(default_factory=list)
