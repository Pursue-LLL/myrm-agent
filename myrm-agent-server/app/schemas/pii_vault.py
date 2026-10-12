"""Pydantic schemas for Client-Side PII Auto-Sanitization and Local Mapping Vault.

[INPUT]
None.

[OUTPUT]
DTO models for PII detection, pseudonymization, and reverse mapping reconstruction.

[POS]
Server schemas. Exposes typed contracts for privacy-preserving PII masking and local vault restoration.
"""

from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class PiiEntityMatchDto(BaseModel):
    """Details of a detected PII entity."""

    model_config = ConfigDict(extra="forbid")

    entity_type: str = Field(..., description="Classification category: chinese_name, phone_number, id_card, etc.")
    raw_value: str = Field(..., description="Original raw PII string")
    placeholder: str = Field(..., description="Assigned pseudonym placeholder")
    start_idx: int = Field(..., description="Start character index in text")
    end_idx: int = Field(..., description="End character index in text")


class SanitizePiiRequest(BaseModel):
    """Payload to scan text and replace PII with session-consistent placeholders."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Raw text containing potential sensitive PII")
    session_id: str = Field(..., description="Target session identifier")


class SanitizePiiResponse(BaseModel):
    """Result of transparent pseudonymization."""

    model_config = ConfigDict(extra="forbid")

    sanitized_text: str = Field(..., description="Anonymized text safe to send to LLM")
    placeholders_count: int = Field(..., description="Total PII instances replaced")
    entities_detected: list[PiiEntityMatchDto] = Field(default_factory=list, description="List of detected entities")
    session_id: str = Field(..., description="Session identifier")
    sanitized_at: float = Field(default_factory=time.time, description="Unix timestamp of sanitization")


class DesanitizePiiRequest(BaseModel):
    """Payload to reverse-replace placeholders in LLM output back to original PII values."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="LLM output text containing placeholders")
    session_id: str = Field(..., description="Target session identifier")


class DesanitizePiiResponse(BaseModel):
    """Result of reverse desanitization."""

    model_config = ConfigDict(extra="forbid")

    restored_text: str = Field(..., description="Text with placeholders restored to original values")
    restored_count: int = Field(..., description="Count of placeholders successfully restored")
    placeholders_found: list[str] = Field(default_factory=list, description="List of unique placeholders restored")
    session_id: str = Field(..., description="Session identifier")
    restored_at: float = Field(default_factory=time.time, description="Unix timestamp of restoration")


class DetectPiiRequest(BaseModel):
    """Payload to probe text for sensitive PII without modifying it."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., description="Text to scan for PII entities")


class DetectPiiResponse(BaseModel):
    """Detection-only report."""

    model_config = ConfigDict(extra="forbid")

    matches: list[PiiEntityMatchDto] = Field(default_factory=list, description="Detected PII entities")
    count: int = Field(..., description="Total entities detected")


class ClearPiiSessionResponse(BaseModel):
    """Confirmation of session mapping wipe."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Target session identifier")
    cleared: bool = Field(..., description="True if session was wiped")
    message: str = Field(..., description="Status summary message")
