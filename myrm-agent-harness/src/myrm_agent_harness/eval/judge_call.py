"""One LLM-judge completion with bounded retry.

[INPUT]
- toolkits.llms.text_completion::acomplete_text (POS: one-shot chat completion as text)
- toolkits.llms.errors.classifier::classify_error (POS: transient vs permanent failure)

[OUTPUT]
- judge_completion: the judge model's answer text for a prompt

[POS]
A judge call is a single deterministic request outside the agent loop, so nothing above it retries: transient
failures (rate limit, overload, timeout, a dropped connection) are retried here a bounded number of times and
anything else (bad credentials, rejected request) surfaces at once.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Final

import httpx

from myrm_agent_harness.toolkits.llms.errors.classifier import ErrorKind, classify_error
from myrm_agent_harness.toolkits.llms.text_completion import acomplete_text

logger = logging.getLogger(__name__)

_RETRIES: Final = 2
_BACKOFF_SECONDS: Final = 1.0
_TRANSIENT: Final = frozenset({ErrorKind.RATE_LIMIT, ErrorKind.OVERLOADED, ErrorKind.TIMEOUT})


def _is_transient(exc: Exception) -> bool:
    return isinstance(exc, httpx.TransportError) or classify_error(exc) in _TRANSIENT


async def judge_completion(
    *,
    model: str,
    prompt: str,
    api_key: str | None = None,
    api_base: str | None = None,
) -> str:
    """The stripped answer text of ``model`` for ``prompt`` (empty when the model returned none)."""
    messages = [{"role": "user", "content": prompt}]

    async def complete() -> str:
        return await acomplete_text(model, messages, api_key=api_key, api_base=api_base, temperature=0.0)

    for attempt in range(_RETRIES):
        try:
            return await complete()
        except Exception as exc:
            if not _is_transient(exc):
                raise
            logger.warning("Judge call attempt %d/%d failed (%s); retrying", attempt + 1, _RETRIES + 1, exc)
            await asyncio.sleep(_BACKOFF_SECONDS * (attempt + 1))
    return await complete()
