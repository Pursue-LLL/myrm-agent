"""OpenInference / GenAI span attributes for one model response.

[INPUT]
- opentelemetry.trace::Span (POS: active span opened by the adapter around one model call)

[OUTPUT]
- record_usage_attributes(): stamps token counts and cache/reasoning details on the span

[POS]
Keeps the attribute vocabulary (OpenInference `llm.*` plus GenAI `gen_ai.*`) next to the
provider-field parsing it depends on, so the adapter states the call, not the naming.
"""

from __future__ import annotations

from typing import Any

from opentelemetry.trace import Span


def record_usage_attributes(
    span: Span,
    *,
    usage: dict[str, Any],
    model_name: str,
) -> None:
    """Stamp token counts, cache read and reasoning details onto ``span``."""
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", 0)

    span.set_attribute("llm.token_count.prompt", prompt_tokens)
    span.set_attribute("llm.token_count.completion", completion_tokens)
    span.set_attribute("llm.token_count.total", total_tokens)

    span.set_attribute("gen_ai.operation.name", "llm.request")
    span.set_attribute("gen_ai.system", "myrm-agent")
    span.set_attribute("gen_ai.request.model", model_name)
    span.set_attribute("gen_ai.usage.input_tokens", prompt_tokens)
    span.set_attribute("gen_ai.usage.output_tokens", completion_tokens)
    span.set_attribute("gen_ai.usage.total_tokens", total_tokens)

    # Prompt cache tokens arrive under a different key per provider.
    cached_tokens = 0
    details = usage.get("prompt_tokens_details")
    if isinstance(details, dict):
        cached_tokens = details.get("cached_tokens", 0)
    else:
        cached_tokens = usage.get("cache_read_input_tokens", 0)
    span.set_attribute("gen_ai.usage.cache_read_tokens", cached_tokens)
    if prompt_tokens:
        span.set_attribute("gen_ai.usage.cache_hit_ratio", round(cached_tokens / prompt_tokens, 4))

    reasoning_tokens = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
    if reasoning_tokens is not None:
        span.set_attribute("gen_ai.usage.reasoning_tokens", reasoning_tokens)


__all__ = ["record_usage_attributes"]
