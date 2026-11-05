"""[OUTPUT]
speed_test endpoints.

[POS]
Batch speed test: first-token latency per configured model.
"""

from __future__ import annotations

import asyncio
import time
from typing import Literal

from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.types import ModelConfig
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.agent.provider_oauth_tokens import resolve_oauth_marker

from .common import _probe_model_kwargs, router


class SpeedTestItemResult(BaseModel):
    """Single model speed test result."""

    model: str = Field(..., description="Model name (LiteLLM format)")
    ttft_ms: int | None = Field(default=None, description="Time to first token in ms")
    throughput_tps: float | None = Field(default=None, description="Tokens per second")
    total_ms: int | None = Field(default=None, description="Total generation time in ms")
    total_tokens: int | None = Field(default=None, description="Total output tokens generated")
    status: Literal["ok", "error"] = Field(..., description="Test outcome")
    error: str | None = Field(default=None, description="Error message if failed")


class SpeedTestRequest(BaseModel):
    """Speed test request — tests specific models with provided credentials."""

    models: list[ModelConfig] = Field(..., description="List of model configs to test")


def _ttft_sort_key(result: dict[str, object]) -> int:
    """Fastest first token first; runs that produced none (failed or timed out) sort last."""
    ttft_ms = result.get("ttft_ms")
    return ttft_ms if isinstance(ttft_ms, int) else 999_999


@router.post("/speed-test", response_model=StandardSuccessResponse)
async def speed_test(request: SpeedTestRequest) -> JSONResponse:
    """Batch speed test for configured models.

    Sequentially sends streaming requests to each model to measure
    TTFT (Time To First Token) and throughput (tokens/s).
    Results are sorted by TTFT ascending.
    """
    from langchain_core.language_models import BaseChatModel
    from langchain_core.messages import HumanMessage
    from myrm_agent_harness.toolkits.llms import llm_manager as llm_tools

    results: list[dict[str, object]] = []

    _SPEED_TEST_TIMEOUT_S = 30.0

    for model_config in request.models:
        kwargs = model_config.model_dump(exclude_none=True)
        kwargs["model_kwargs"] = _probe_model_kwargs(kwargs.get("model_kwargs") or {})
        try:
            await resolve_oauth_marker(kwargs)
            llm = await llm_tools.get_llm(**kwargs)
            message = HumanMessage(content="Count from 1 to 20")

            first_token_time: float | None = None
            token_count = 0
            start = time.monotonic()

            async def _stream_and_measure(stream_llm: BaseChatModel, stream_msg: HumanMessage) -> None:
                nonlocal first_token_time, token_count
                async for chunk in stream_llm.astream([stream_msg], config={"tags": ["speed_test"]}):
                    if chunk.content:
                        if first_token_time is None:
                            first_token_time = time.monotonic()
                        token_count += 1

            await asyncio.wait_for(_stream_and_measure(llm, message), timeout=_SPEED_TEST_TIMEOUT_S)
            total_elapsed = time.monotonic() - start

            if first_token_time is None:
                results.append(
                    SpeedTestItemResult(
                        model=model_config.model,
                        status="error",
                        error="No tokens received",
                    ).model_dump()
                )
                continue

            ttft_ms = int((first_token_time - start) * 1000)
            total_ms = int(total_elapsed * 1000)
            generation_time = total_elapsed - (first_token_time - start)
            tps = round(token_count / generation_time, 1) if generation_time > 0 else 0.0

            results.append(
                SpeedTestItemResult(
                    model=model_config.model,
                    ttft_ms=ttft_ms,
                    throughput_tps=tps,
                    total_ms=total_ms,
                    total_tokens=token_count,
                    status="ok",
                ).model_dump()
            )
        except asyncio.TimeoutError:
            results.append(
                SpeedTestItemResult(
                    model=model_config.model,
                    status="error",
                    error=f"Timed out after {_SPEED_TEST_TIMEOUT_S:.0f}s",
                ).model_dump()
            )
        except Exception as e:
            results.append(
                SpeedTestItemResult(
                    model=model_config.model,
                    status="error",
                    error=f"{type(e).__name__}: {e!s}"[:200],
                ).model_dump()
            )

    results.sort(key=_ttft_sort_key)
    return success_response(data=results)
