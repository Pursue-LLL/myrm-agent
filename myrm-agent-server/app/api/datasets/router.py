"""Dataset export REST API endpoints.

Provides HTTP endpoints for exporting event log traces as fine-tuning datasets
in ShareGPT, Alpaca, or OpenAI JSONL formats.

[INPUT]
- myrm_agent_harness.agent.event_log.dataset_export (POS: Dataset export pipeline)
- myrm_agent_harness.agent.event_log.backends.file_backend (POS: Built-in JSONL backend)
- app.config.settings::settings (POS: 统一配置中心)

[OUTPUT]
- POST /export: trigger a dataset export
- GET /formats: list available export formats
- GET /reports/{filename}: download an exported JSONL file

[POS]
HTTP thin layer for dataset export. All heavy logic in harness.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from app.config.settings import settings
from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class ExportRequest(BaseModel):
    """Request body for triggering a dataset export."""

    formats: list[str] = Field(
        default=["sharegpt"],
        description="Output formats: sharegpt, alpaca, openai",
    )
    redact_pii: bool = Field(default=True, description="Apply PII redaction")
    max_samples: int = Field(default=0, ge=0, description="Max samples (0=unlimited)")
    require_success: bool = Field(default=True, description="Only export successful traces")
    min_turns: int = Field(default=2, ge=0, description="Minimum conversation turns")
    min_content_length: int = Field(default=50, ge=0, description="Minimum content length")
    start_time: float | None = Field(default=None, description="Filter: start UTC timestamp")
    end_time: float | None = Field(default=None, description="Filter: end UTC timestamp")
    incremental: bool = Field(default=False, description="Enable incremental export")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/formats")
async def list_export_formats() -> JSONResponse:
    """List available dataset export formats."""
    from myrm_agent_harness.agent.event_log.dataset_export import ExportFormat

    return success_response(
        data={
            "formats": [
                {
                    "id": fmt.value,
                    "name": _FORMAT_DISPLAY_NAMES.get(fmt.value, fmt.value),
                    "description": _FORMAT_DESCRIPTIONS.get(fmt.value, ""),
                }
                for fmt in ExportFormat
            ]
        }
    )


@router.post("/export")
async def trigger_export(body: ExportRequest) -> JSONResponse:
    """Trigger a dataset export from event logs.

    Reads all event log sessions, applies quality filtering and PII redaction,
    then writes JSONL files in the requested formats.
    """
    event_log_dir = Path(settings.database.event_log_dir)
    if not event_log_dir.exists():
        raise validation_error("Event log directory does not exist. No data to export.")

    from myrm_agent_harness.agent.event_log.backends.file_backend import FileEventLogBackend
    from myrm_agent_harness.agent.event_log.dataset_export import (
        DatasetExporter,
        ExportConfig,
        ExportFormat,
        ExportReport,
    )
    from myrm_agent_harness.agent.event_log.dataset_export.protocols import QualityThresholds

    parsed_formats: list[ExportFormat] = []
    for fmt_str in body.formats:
        try:
            parsed_formats.append(ExportFormat(fmt_str.lower()))
        except ValueError as exc:
            valid = ", ".join(f.value for f in ExportFormat)
            raise validation_error(f"Unknown format '{fmt_str}'. Valid: {valid}") from exc

    if not parsed_formats:
        raise validation_error("At least one export format is required.")

    output_dir = event_log_dir.parent / "dataset_exports"
    incremental_file = output_dir / ".export_state.json" if body.incremental else None

    config = ExportConfig(
        output_dir=output_dir,
        formats=tuple(parsed_formats),
        quality=QualityThresholds(
            require_success=body.require_success,
            min_turns=body.min_turns,
            min_content_length=body.min_content_length,
        ),
        redact_pii=body.redact_pii,
        max_samples=body.max_samples,
        start_time=body.start_time,
        end_time=body.end_time,
        incremental_state_file=incremental_file,
    )

    try:
        backend = FileEventLogBackend(log_dir=event_log_dir, session_id="export")
        exporter = DatasetExporter(backend)
        report: ExportReport = await exporter.export(config)
        return success_response(data=report.to_dict())
    except Exception as e:
        raise internal_error(operation="Dataset export", exception=e) from e


@router.get("/files")
async def list_export_files() -> JSONResponse:
    """List available exported dataset files."""
    export_dir = Path(settings.database.event_log_dir).parent / "dataset_exports"
    if not export_dir.exists():
        return success_response(data={"files": []})

    files: list[dict[str, object]] = []
    for f in sorted(export_dir.glob("dataset_*.jsonl")):
        stat = f.stat()
        line_count = sum(1 for _ in f.open("r", encoding="utf-8"))
        files.append(
            {
                "name": f.name,
                "format": f.stem.replace("dataset_", ""),
                "size_bytes": stat.st_size,
                "line_count": line_count,
                "modified_at": stat.st_mtime,
            }
        )

    return success_response(data={"files": files})


@router.get("/files/{filename}")
async def download_export_file(filename: str) -> FileResponse:
    """Download an exported dataset JSONL file."""
    if not filename.startswith("dataset_") or not filename.endswith(".jsonl"):
        raise validation_error("Invalid filename format. Expected: dataset_<format>.jsonl")

    export_dir = Path(settings.database.event_log_dir).parent / "dataset_exports"
    file_path = export_dir / filename

    if not file_path.exists() or not file_path.is_file():
        raise validation_error(f"File not found: {filename}")

    if not file_path.resolve().is_relative_to(export_dir.resolve()):
        raise validation_error("Path traversal detected")

    return FileResponse(
        path=file_path,
        filename=filename,
        media_type="application/jsonl",
    )


# ---------------------------------------------------------------------------
# Display metadata (populated lazily to avoid top-level import of dataset_export)
# ---------------------------------------------------------------------------

_FORMAT_DISPLAY_NAMES: dict[str, str] = {
    "sharegpt": "ShareGPT",
    "alpaca": "Alpaca",
    "openai": "OpenAI Chat",
}

_FORMAT_DESCRIPTIONS: dict[str, str] = {
    "sharegpt": "Multi-turn conversation format with human/gpt/tool roles. Compatible with LLaMA-Factory.",
    "alpaca": "Instruction-following format (instruction/input/output). Compatible with Alpaca-LoRA.",
    "openai": "OpenAI chat completions format with system/user/assistant/tool messages. Compatible with OpenAI fine-tuning API.",
}
