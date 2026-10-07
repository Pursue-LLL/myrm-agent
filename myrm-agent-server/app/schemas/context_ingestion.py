"""[POS]: app/schemas/context_ingestion.py
[INPUT]: Request and response parameters for context ingestion gateway and hardware sync endpoints.
[OUTPUT]: Strongly typed Pydantic models for ingesting transcripts, webhooks, and querying ingestion history.
"""

from pydantic import BaseModel, Field


class IngestContextRequest(BaseModel):
    """Request payload to ingest multi-source audio transcript or meeting log."""

    source_type: str = Field(
        default="raw_transcript",
        description="Protocol format: plaud_voice_card, webvtt, srt, raw_transcript, webhook",
    )
    device_id: str = Field(default="unknown_device", description="Identifier of recording device or source")
    title: str = Field(default="Untitled Audio Recording", description="Recording title or meeting topic")
    raw_payload: str = Field(..., description="Raw text, JSON, WebVTT, or SRT string")
    session_id: str | None = Field(default=None, description="Optional target session ID to attach")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom contextual metadata tags")


class IngestContextResponse(BaseModel):
    """Response payload containing distilled summary, action items, decisions, and dedup state."""

    fingerprint: str = Field(..., description="SHA-256 deduplication fingerprint")
    title: str = Field(..., description="Title of the voice recording")
    source_type: str = Field(..., description="Protocol format used")
    speaker_count: int = Field(default=0, ge=0, description="Total distinct speakers detected")
    segment_count: int = Field(default=0, ge=0, description="Total normalized segments extracted")
    summary: str = Field(default="", description="High-level structured summary")
    action_items: list[str] = Field(default_factory=list, description="Extracted action items")
    decisions: list[str] = Field(default_factory=list, description="Extracted architectural decisions")
    is_duplicate: bool = Field(default=False, description="Whether the payload was duplicate and skipped")
    created_at_epoch: float = Field(..., description="Epoch timestamp of ingestion")


class PlaudWebhookRequest(BaseModel):
    """Payload format delivered by Plaud voice recorder cloud webhook."""

    device_id: str = Field(..., description="Plaud hardware card serial number or client ID")
    meeting_title: str = Field(default="Plaud Card Sync", description="Meeting title")
    transcription_json: str = Field(..., description="Plaud JSON transcription payload")
    tags: dict[str, str] = Field(default_factory=dict, description="Metadata tags")


class IngestionHistoryItem(BaseModel):
    """Historical context ingestion entry."""

    fingerprint: str = Field(..., description="Deduplication fingerprint")
    source_type: str = Field(..., description="Source protocol type")
    device_id: str = Field(..., description="Device ID")
    title: str = Field(..., description="Recording title")
    created_at_epoch: float = Field(..., description="Epoch timestamp")


class IngestionHistoryResponse(BaseModel):
    """Response payload listing recent ingestion history records."""

    items: list[IngestionHistoryItem] = Field(default_factory=list, description="Recent ingestion records")
    total: int = Field(..., description="Total records returned")


class SupportedFormatsResponse(BaseModel):
    """Response payload listing supported context ingestion formats."""

    formats: list[str] = Field(..., description="List of supported format identifiers")
    description: dict[str, str] = Field(..., description="Explanation of each format")
