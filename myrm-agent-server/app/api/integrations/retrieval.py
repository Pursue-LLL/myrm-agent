"""Retrieval service validation API.

[INPUT]
- myrm_agent_harness.toolkits.retriever.embedding.factory::get_embedding_service (POS: embedding service factory)
- myrm_agent_harness.toolkits.retriever.reranker.factory::get_reranker_service (POS: reranker service factory)
- myrm_agent_harness.toolkits.llms.errors::classify_failover_reason (POS: provider failure classifier)

[OUTPUT]
- validate_embedding: POST /embedding, embeds one short text through the configured provider
- validate_reranker: POST /reranker, reranks two short documents through the configured provider

[POS]
Settings probes an embedding or reranker configuration with one real call before applying it. The probe goes through the
factories the product builds its services with, so what validates is what the product then reuses. A refused probe is
still an HTTP 200 carrying `success=False` and a message that names the cause: the settings UI shows `message` as is.
Every probe carries a text no earlier call used, so no cache keyed by the text can answer it in place of the provider.
"""

from __future__ import annotations

import logging
import uuid

import httpx
from fastapi import APIRouter
from myrm_agent_harness.toolkits.llms.errors import FailoverReason, classify_failover_reason
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig, get_embedding_service
from myrm_agent_harness.toolkits.retriever.reranker.factory import RerankerConfig, get_reranker_service
from pydantic import BaseModel, Field

router = APIRouter()
logger = logging.getLogger(__name__)

_PROBE_DOCUMENTS = ["doc1", "doc2"]

_CAUSES: dict[FailoverReason, str] = {
    FailoverReason.AUTH_PERMANENT: "the provider rejected the API key",
    FailoverReason.MODEL_NOT_FOUND: "the provider does not know this model or endpoint",
    FailoverReason.RATE_LIMIT: "the provider rate-limited the request",
    FailoverReason.BILLING: "the provider account has no quota or balance left",
    FailoverReason.TIMEOUT: "the provider endpoint could not be reached",
    FailoverReason.TLS_CERTIFICATE: "the provider's TLS certificate was rejected",
}


class RetrievalProbeRequest(BaseModel):
    """Embedding or reranker configuration to probe."""

    model: str = Field(..., description="Model name in LiteLLM format")
    api_key: str = Field(..., description="API key")
    api_base: str | None = Field(default=None, description="Custom API endpoint")
    provider: str | None = Field(
        default=None, description="Retrieval provider id; the control plane reads it to find the upstream endpoint"
    )


class ValidationResult(BaseModel):
    """Outcome of a probe."""

    success: bool = Field(..., description="Whether the provider answered the probe")
    message: str = Field(..., description="Outcome naming the cause of a failure")
    error: str | None = Field(default=None, description="Exception text of a refused probe, without the API key")


def _probe_text() -> str:
    """A text no earlier call used.

    A cache keyed by model and input (an embedding service's own, a gateway's) would answer a repeated text after one
    success, and a key or endpoint edited since would still validate.
    """
    return f"probe-{uuid.uuid4().hex}"


def _failed(cause: str, error: str | None = None) -> ValidationResult:
    return ValidationResult(success=False, message=f"Validation failed: {cause}", error=error)


def _http_status(exc: Exception) -> int | None:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code
    status = getattr(exc, "status_code", None)  # LiteLLM and OpenAI SDK errors carry the provider's status
    return status if isinstance(status, int) else None


def _explain(exc: Exception) -> str:
    """Name what a refused probe means for the settings form; the classifier misses a bare 404 and httpx transport errors."""
    reason = classify_failover_reason(exc)
    if _http_status(exc) == 404:
        reason = FailoverReason.MODEL_NOT_FOUND
    elif isinstance(exc, httpx.TransportError):
        reason = FailoverReason.TIMEOUT
    return _CAUSES.get(reason, type(exc).__name__)


def _refused(kind: str, request: RetrievalProbeRequest, exc: Exception) -> ValidationResult:
    cause = _explain(exc)
    logger.warning("%s validation failed for model %s: %s (%s)", kind, request.model, cause, type(exc).__name__)
    # Providers may repeat the key in an error body: it must not travel back.
    return _failed(cause, str(exc).replace(request.api_key, "***"))


@router.post("/embedding", response_model=ValidationResult, summary="Validate embedding configuration")
async def validate_embedding(request: RetrievalProbeRequest) -> ValidationResult:
    """Embed one short text through the configured provider."""
    if not request.api_key:
        return _failed("an API key is required")
    service = get_embedding_service(EmbeddingConfig(model=request.model, api_key=request.api_key, api_base=request.api_base))
    try:
        vector = await service.embed(_probe_text())
    except Exception as exc:
        return _refused("Embedding", request, exc)
    if not vector:
        return _failed("the provider returned no embedding")
    return ValidationResult(success=True, message=f"Validation successful (dimension: {len(vector)})")


@router.post("/reranker", response_model=ValidationResult, summary="Validate reranker configuration")
async def validate_reranker(request: RetrievalProbeRequest) -> ValidationResult:
    """Rerank two short documents through the configured provider."""
    if not request.api_key:
        return _failed("an API key is required")
    service = get_reranker_service(RerankerConfig(model=request.model, api_key=request.api_key, api_base=request.api_base))
    try:
        hits = await service.rerank(_probe_text(), _PROBE_DOCUMENTS, top_k=1)
    except Exception as exc:
        return _refused("Reranker", request, exc)
    if not hits:
        return _failed("the provider returned no results")
    return ValidationResult(
        success=True, message=f"Validation successful (returned {len(hits)} result{'s' if len(hits) > 1 else ''})"
    )
