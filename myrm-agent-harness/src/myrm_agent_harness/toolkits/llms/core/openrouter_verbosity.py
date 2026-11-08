"""OpenRouter reasoning_effort → reasoning.effort parameter mapping.

[INPUT]
- (none, stateless utility)

[OUTPUT]
- apply_openrouter_reasoning_effort(): rewrite reasoning_effort into
  OpenRouter's ``extra_body.reasoning.effort`` format for models routed
  through OpenRouter.

[POS]
OpenRouter accepts reasoning effort via the nested ``reasoning.effort``
field (or the top-level ``verbosity`` alias), **not** the OpenAI-style
top-level ``reasoning_effort``, so the parameter format the OpenAI wire
sends by default is wrong for OpenRouter.

This module bridges the gap at LLM-creation time: when the model is
routed through OpenRouter and ``reasoning_effort`` is present in kwargs,
it rewrites it into ``extra_body.reasoning.effort`` — the format
OpenRouter documents for all reasoning-capable models.

See: https://openrouter.ai/docs/guides/best-practices/reasoning-tokens
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

_OPENROUTER_PREFIX = "openrouter/"


def _is_openrouter_model(model: str) -> bool:
    return model.startswith(_OPENROUTER_PREFIX)


def apply_openrouter_reasoning_effort(model: str, llm_kwargs: dict[str, Any]) -> None:
    """Rewrite ``reasoning_effort`` into OpenRouter's ``reasoning.effort`` format.

    When the model is routed through OpenRouter and ``reasoning_effort``
    is present (either at the top level or inside ``extra_body``), this
    rewrites it into ``extra_body.reasoning = {"effort": <value>}`` and
    removes the stale top-level / flat ``reasoning_effort`` key.

    For non-OpenRouter models or when no ``reasoning_effort`` is present,
    this is a no-op.

    Args:
        model: Full route model identifier (e.g. ``openrouter/anthropic/claude-4.6-opus``).
        llm_kwargs: Mutable LLM parameter dict (modified in place).
    """
    if not _is_openrouter_model(model):
        return

    effort = llm_kwargs.pop("reasoning_effort", None)

    extra_body: dict[str, Any] = llm_kwargs.get("extra_body", {})
    if effort is None:
        effort = extra_body.pop("reasoning_effort", None)

    if effort is None:
        return

    if not isinstance(extra_body, dict):
        extra_body = {}
    extra_body.pop("reasoning_effort", None)

    reasoning = extra_body.get("reasoning")
    if isinstance(reasoning, dict):
        reasoning["effort"] = effort
    else:
        extra_body["reasoning"] = {"effort": effort}

    llm_kwargs["extra_body"] = extra_body

    logger.info(
        "OpenRouter reasoning rewrite: reasoning_effort=%s → reasoning.effort for %s",
        effort,
        model,
    )
