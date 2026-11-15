"""Thinking switches in the dialect of the gateways that document their own.

[INPUT]
- core.reasoning_route::resolve_reasoning_route (POS: provider, bare model id, gateway and body shape of one call)
- core.reasoning_profile::extract_reasoning_effort / is_disabled_effort (POS: the reasoning intent a request carries)

[OUTPUT]
- apply_gateway_thinking(): rewrites an explicit thinking choice into the switch the call's gateway documents

[POS]
Every OpenAI-shaped gateway carries ``reasoning_effort`` the same way, but the switch that turns thinking on or off
differs per host. Only an explicit choice is rewritten (an effort level, ``off``, or a ``thinking`` object); a request
that selects nothing keeps the gateway's own default untouched. What each gateway documents:

- SiliconFlow (https://docs.siliconflow.cn/en/api-reference/chat-completions/chat-completions): a boolean
  ``enable_thinking`` for most reasoning models and no ``thinking`` object; ``reasoning_effort`` (``high`` / ``max``,
  lower and ``xhigh`` levels mapped by the gateway) only for DeepSeek V4 and GLM-5.2, whose levels the generic rules
  already carry. So only ``off`` and an explicit ``thinking`` object are rewritten; a depth level is left as it is,
  because no switch is documented for turning thinking on at a depth, and every request that names ``low`` (the lite
  model of every agent run does) would otherwise start thinking on models that do not think by default.
- NVIDIA hosted API, DeepSeek V4 (https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-pro-infer): the
  thinking switch and its level travel in ``chat_template_kwargs``; a top-level ``reasoning_effort`` is documented but
  ignored by V4 Pro. Only ``none`` / ``high`` / ``max`` are documented, so a lower level sends nothing rather than a
  value the gateway never defined. Other NVIDIA models keep the generic rules.

These rules follow the gateways' documentation; they have not been exercised against the live gateways.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass

from myrm_agent_harness.toolkits.llms.core.reasoning_profile import extract_reasoning_effort, is_disabled_effort
from myrm_agent_harness.toolkits.llms.core.reasoning_route import resolve_reasoning_route

logger = logging.getLogger(__name__)

_NVIDIA_DEEPSEEK_V4 = "deepseek-v4"
# Levels of the reasoning_effort enum NVIDIA documents for DeepSeek V4; ``xhigh`` / ``ultra`` are DeepSeek's own aliases of ``max``.
_NVIDIA_HIGH_LEVELS: frozenset[str] = frozenset({"high"})
_NVIDIA_MAX_LEVELS: frozenset[str] = frozenset({"max", "xhigh", "ultra"})


@dataclass(frozen=True, slots=True)
class _Choice:
    """What the caller asked for: thinking on (at ``level``, if it named one) or off."""

    enabled: bool
    level: str | None = None


def _explicit_choice(llm_kwargs: Mapping[str, object], extra_body: Mapping[str, object]) -> _Choice | None:
    """The thinking choice a request states, or None when it selects nothing."""
    effort = extract_reasoning_effort(llm_kwargs)
    thinking = extra_body.get("thinking")
    thinking_type = thinking.get("type") if isinstance(thinking, Mapping) else thinking
    if is_disabled_effort(effort) or thinking_type == "disabled" or thinking_type is False:
        return _Choice(enabled=False)
    if effort is not None:
        return _Choice(enabled=True, level=effort)
    if thinking_type == "enabled" or thinking_type is True:
        return _Choice(enabled=True)
    return None


def _drop(llm_kwargs: dict[str, object], extra_body: dict[str, object], *keys: str) -> None:
    """Remove ``keys`` from the top level and from ``extra_body``, where the factory mirrors them."""
    for key in keys:
        llm_kwargs.pop(key, None)
        extra_body.pop(key, None)


def _siliconflow(choice: _Choice, llm_kwargs: dict[str, object], extra_body: dict[str, object]) -> None:
    extra_body.setdefault("enable_thinking", choice.enabled)
    _drop(llm_kwargs, extra_body, "thinking", "reasoning_effort")


def _nvidia_deepseek_v4(choice: _Choice, llm_kwargs: dict[str, object], extra_body: dict[str, object]) -> None:
    switch: dict[str, object] = {}
    if not choice.enabled:
        switch = {"thinking": False}
    elif choice.level is None:
        switch = {"thinking": True}
    elif choice.level in _NVIDIA_HIGH_LEVELS:
        switch = {"thinking": True, "reasoning_effort": "high"}
    elif choice.level in _NVIDIA_MAX_LEVELS:
        switch = {"thinking": True, "reasoning_effort": "max"}
    current = extra_body.get("chat_template_kwargs")
    template_kwargs = {**switch, **(current if isinstance(current, dict) else {})}  # the caller's own keys win
    if template_kwargs:
        extra_body["chat_template_kwargs"] = template_kwargs
    _drop(llm_kwargs, extra_body, "thinking", "reasoning_effort")


def apply_gateway_thinking(model: str, llm_kwargs: dict[str, object]) -> None:
    """Rewrite an explicit thinking choice into the switch the call's gateway documents, in place.

    A call to any other endpoint, and a request that states no choice, is left exactly as it is.
    """
    base_url = llm_kwargs.get("api_base") or llm_kwargs.get("base_url")
    custom_provider = llm_kwargs.get("custom_llm_provider")
    route = resolve_reasoning_route(
        model,
        base_url if isinstance(base_url, str) else None,
        custom_provider if isinstance(custom_provider, str) else None,
    )
    if route is None or route.gateway is None or not route.openai_body:
        return
    is_nvidia_v4 = route.gateway == "nvidia" and _NVIDIA_DEEPSEEK_V4 in route.model
    if route.gateway == "nvidia" and not is_nvidia_v4:
        return

    current = llm_kwargs.get("extra_body")
    extra_body = dict(current) if isinstance(current, dict) else {}
    choice = _explicit_choice(llm_kwargs, extra_body)
    if choice is None or (route.gateway == "siliconflow" and choice.enabled and choice.level is not None):
        return

    # The caller's extra_body is copied, never edited: it may be shared with the model configuration.
    llm_kwargs["extra_body"] = extra_body
    if route.gateway == "siliconflow":
        _siliconflow(choice, llm_kwargs, extra_body)
    else:
        _nvidia_deepseek_v4(choice, llm_kwargs, extra_body)
    logger.debug("Gateway thinking rewritten: model=%s gateway=%s enabled=%s", model, route.gateway, choice.enabled)
