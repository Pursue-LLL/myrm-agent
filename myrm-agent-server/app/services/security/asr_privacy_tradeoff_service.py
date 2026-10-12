"""Service layer for ASR Privacy Tradeoff management.

[INPUT]
- myrm_agent_harness.core.security.asr_privacy_tradeoff::AsrPrivacyTradeoffController (POS: Core controller enforcing acoustic destruction tradeoffs)
- app.schemas.asr_privacy_tradeoff::EvaluateAudioPolicyRequest (POS: Request schemas for ASR policy evaluation)

[OUTPUT]
- AsrPrivacyTradeoffService: Evaluates acoustic privacy tradeoffs and coordinates transcription cleanup.

[POS]
Service layer bridging ASR audio lifecycle policies to FastAPI endpoints.
"""

from __future__ import annotations

from myrm_agent_harness.core.security.asr_privacy_tradeoff import (
    AsrPrivacyTradeoffController,
    AudioRetentionPolicy,
    AudioTranscriptionJob,
)

from app.schemas.asr_privacy_tradeoff import (
    EvaluateAudioPolicyRequest,
    EvaluateAudioPolicyResponse,
    ProcessTranscriptionCleanupRequest,
)


class AsrPrivacyTradeoffService:
    """Service wrapping ASR lifecycle zero-retention policies and tradeoff disclosures."""

    def evaluate_policy(
        self, request: EvaluateAudioPolicyRequest
    ) -> EvaluateAudioPolicyResponse:
        """Evaluate privacy tradeoff for an audio retention policy."""
        policy_enum = AudioRetentionPolicy(request.retention_policy)
        decision = AsrPrivacyTradeoffController.evaluate_policy(
            policy=policy_enum,
            user_confirmed=request.user_confirmed,
        )
        return EvaluateAudioPolicyResponse(
            retention_policy=decision.retention_policy.value,
            raw_audio_purged=decision.raw_audio_purged,
            speaker_capability=decision.speaker_capability.value,
            privacy_disclosure_confirmed=decision.privacy_disclosure_confirmed,
            tradeoff_warning=decision.tradeoff_warning,
            explanation=decision.explanation,
        )

    def process_cleanup(
        self, request: ProcessTranscriptionCleanupRequest
    ) -> EvaluateAudioPolicyResponse:
        """Execute post-transcription zero-retention audio cleanup."""
        policy_enum = AudioRetentionPolicy(request.retention_policy)
        job = AudioTranscriptionJob(
            job_id=request.job_id,
            audio_bytes_length=request.audio_bytes_length,
            retention_policy=policy_enum,
            consent_given=request.consent_given,
        )
        decision = AsrPrivacyTradeoffController.process_transcription_cleanup(job)
        return EvaluateAudioPolicyResponse(
            retention_policy=decision.retention_policy.value,
            raw_audio_purged=decision.raw_audio_purged,
            speaker_capability=decision.speaker_capability.value,
            privacy_disclosure_confirmed=decision.privacy_disclosure_confirmed,
            tradeoff_warning=decision.tradeoff_warning,
            explanation=decision.explanation,
        )


_instance: AsrPrivacyTradeoffService | None = None


def get_asr_privacy_tradeoff_service() -> AsrPrivacyTradeoffService:
    """Get singleton instance of AsrPrivacyTradeoffService."""
    global _instance
    if _instance is None:
        _instance = AsrPrivacyTradeoffService()
    return _instance
