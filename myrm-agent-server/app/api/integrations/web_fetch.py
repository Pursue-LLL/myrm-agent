"""Web fetch escalation verify API.

[INPUT]
- app.services.web_fetch.providers.firecrawl::FirecrawlEscalationProvider (POS: Firecrawl remote fetch)
- app.services.web_fetch.providers.jina::JinaEscalationProvider (POS: Jina Reader remote fetch)

[OUTPUT]
- verify_web_fetch_escalation: POST /verify endpoint for credential verification.

[POS]
REST API for verifying remote web fetch provider credentials (Jina/Firecrawl).
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import external_service_error, validation_error
from app.core.utils.response_utils import success_response
from app.database.standard_responses import StandardSuccessResponse
from app.services.web_fetch.providers.firecrawl import FirecrawlEscalationProvider
from app.services.web_fetch.providers.jina import JinaEscalationProvider

logger = logging.getLogger(__name__)

router = APIRouter()

_VERIFY_URL = "https://example.com"


class WebFetchEscalationVerifyRequest(BaseModel):
    provider: Literal["jina", "firecrawl"] = Field(..., description="Remote reader provider to verify")
    api_key: str | None = Field(None, description="Optional Jina API key; required for Firecrawl")
    test_url: str | None = Field(None, description="URL to fetch for verification")


class WebFetchEscalationVerifyData(BaseModel):
    provider: str
    content_length: int
    title: str = ""


@router.post("/verify", response_model=StandardSuccessResponse)
async def verify_web_fetch_escalation(request: WebFetchEscalationVerifyRequest) -> JSONResponse:
    """Verify Jina or Firecrawl credentials by fetching a test page."""
    test_url = (request.test_url or _VERIFY_URL).strip()
    if not test_url:
        raise validation_error("test_url is required")

    try:
        if request.provider == "jina":
            provider: JinaEscalationProvider | FirecrawlEscalationProvider = JinaEscalationProvider(
                api_key=request.api_key
            )
        else:
            if not (request.api_key or "").strip():
                raise validation_error("API key is required for Firecrawl verification")
            provider = FirecrawlEscalationProvider(request.api_key or "")

        result = await provider.fetch_url(test_url, max_chars=4000)
        if result is None or not result.content.strip():
            raise external_service_error(request.provider, "Remote fetch returned empty content")

        data = WebFetchEscalationVerifyData(
            provider=request.provider,
            content_length=len(result.content),
            title=result.title,
        )
        return success_response(data=data.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Web fetch escalation verify failed: %s", exc)
        raise external_service_error(request.provider, str(exc)) from exc
