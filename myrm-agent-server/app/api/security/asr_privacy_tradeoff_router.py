"""API router for ASR Privacy Tradeoff management.

[INPUT]
- app.services.security.asr_privacy_tradeoff_service::AsrPrivacyTradeoffService (POS: Evaluates acoustic privacy tradeoffs)

[OUTPUT]
- APIRouter handling /asr-privacy-tradeoff endpoints for evaluate-policy and process-cleanup.

[POS]
HTTP routing layer for ASR voice privacy tradeoff evaluation and audio zero-retention shredding.
"""

from fastapi import APIRouter, Depends

from app.schemas.asr_privacy_tradeoff import (
    EvaluateAudioPolicyRequest,
    EvaluateAudioPolicyResponse,
    ProcessTranscriptionCleanupRequest,
)
from app.services.security.asr_privacy_tradeoff_service import (
    AsrPrivacyTradeoffService,
    get_asr_privacy_tradeoff_service,
)

router = APIRouter(
    prefix="/asr-privacy-tradeoff", tags=["security", "asr-privacy-tradeoff"]
)


@router.post("/evaluate-policy", response_model=EvaluateAudioPolicyResponse)
async def evaluate_audio_policy(
    request: EvaluateAudioPolicyRequest,
    service: AsrPrivacyTradeoffService = Depends(get_asr_privacy_tradeoff_service),
) -> EvaluateAudioPolicyResponse:
    """Evaluate privacy tradeoffs and speaker capability impacts for audio retention."""
    return service.evaluate_policy(request)


@router.post("/process-cleanup", response_model=EvaluateAudioPolicyResponse)
async def process_transcription_cleanup(
    request: ProcessTranscriptionCleanupRequest,
    service: AsrPrivacyTradeoffService = Depends(get_asr_privacy_tradeoff_service),
) -> EvaluateAudioPolicyResponse:
    """Enforce zero-retention raw audio shredding upon transcription completion."""
    return service.process_cleanup(request)
