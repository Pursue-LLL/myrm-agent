"""Schemas for ASR Privacy Tradeoff management."""

from typing import Literal

from pydantic import BaseModel, Field


class EvaluateAudioPolicyRequest(BaseModel):
    """Request to evaluate the privacy tradeoff of an audio retention policy."""

    retention_policy: Literal[
        "ephemeral_transcript_only",
        "retain_voice_embeddings_only",
        "full_persistence",
    ] = Field(
        default="ephemeral_transcript_only",
        description="Desired audio retention policy",
    )
    user_confirmed: bool = Field(
        default=True,
        description="Whether user has reviewed and acknowledged the privacy/speaker tradeoff",
    )


class EvaluateAudioPolicyResponse(BaseModel):
    """Evaluation response indicating privacy impact and capability tradeoffs."""

    retention_policy: str
    raw_audio_purged: bool
    speaker_capability: str
    privacy_disclosure_confirmed: bool
    tradeoff_warning: str | None
    explanation: str


class ProcessTranscriptionCleanupRequest(BaseModel):
    """Request to process cleanup after ASR transcription job."""

    job_id: str = Field(..., description="Unique ASR job ID")
    audio_bytes_length: int = Field(..., description="Length of processed audio stream")
    retention_policy: Literal[
        "ephemeral_transcript_only",
        "retain_voice_embeddings_only",
        "full_persistence",
    ] = Field(default="ephemeral_transcript_only")
    consent_given: bool = Field(default=True)
