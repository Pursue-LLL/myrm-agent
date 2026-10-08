"""Service provider for Pluggable Context Hook Pipeline & Memory Injection.

[POS]
Maintains singleton ContextHookPipelineSuite instance with built-in
lifecycle interceptors and dual-layer memory weaving.

[INPUT]
- myrm_agent_harness.toolkits.memory

[OUTPUT]
- get_context_hook_suite, reset_context_hook_suite
"""

from __future__ import annotations

import re

from myrm_agent_harness.toolkits.memory import (
    ContextEnvelope,
    ContextHookPipelineSuite,
    ContextHookStage,
    HookExecutionPriority,
)

_SUITE_INSTANCE: ContextHookPipelineSuite | None = None

_REDACT_SECRET_PATTERN = re.compile(
    r"(?:sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|password\s*[:=]\s*\S+)",
    re.IGNORECASE,
)


def _env_guard_hook(env: ContextEnvelope) -> bool:
    """Inject sandbox runtime telemetry context before agent starts."""
    env.metadata["runtime_fence"] = "sandbox_hardened"
    return True


def _prompt_enrich_hook(env: ContextEnvelope) -> bool:
    """Enrich system prompt with active agent persona markers."""
    if f"[Active Agent: {env.agent_id}]" not in env.system_prompt:
        env.system_prompt += f"\n[Active Agent: {env.agent_id}]"
        return True
    return False


def _egress_redactor_hook(env: ContextEnvelope) -> bool:
    """Redact leaked credentials or tokens before sending request to LLM."""
    if _REDACT_SECRET_PATTERN.search(env.system_prompt):
        env.system_prompt = _REDACT_SECRET_PATTERN.sub("[REDACTED_SECRET]", env.system_prompt)
        env.metadata["egress_redacted"] = "true"
        return True
    return False


def _create_prepopulated_suite() -> ContextHookPipelineSuite:
    """Instantiate and register standard security, memory, and enrich hooks."""
    suite = ContextHookPipelineSuite()

    # 1. Before Agent Start
    suite.register_hook(
        hook_id="builtin_env_guard",
        stage=ContextHookStage.BEFORE_AGENT_START,
        handler=_env_guard_hook,
        priority=int(HookExecutionPriority.SECURITY_FIRST) + 5,
        description="Injects hardened sandbox runtime telemetry headers",
    )

    # 2. Context Transform
    suite.register_hook(
        hook_id="builtin_prompt_enrich",
        stage=ContextHookStage.CONTEXT_TRANSFORM,
        handler=_prompt_enrich_hook,
        priority=int(HookExecutionPriority.USER_CUSTOM) - 5,
        description="Decorates system prompt with agent persona metadata",
    )

    # 3. Before LLM Request (Egress Security)
    suite.register_hook(
        hook_id="builtin_egress_redactor",
        stage=ContextHookStage.BEFORE_LLM_REQUEST,
        handler=_egress_redactor_hook,
        priority=int(HookExecutionPriority.SECURITY_FIRST),
        description="Redacts sensitive API keys and tokens before egress",
    )

    return suite


def get_context_hook_suite() -> ContextHookPipelineSuite:
    """Retrieve the singleton ContextHookPipelineSuite instance."""
    global _SUITE_INSTANCE
    if _SUITE_INSTANCE is None:
        _SUITE_INSTANCE = _create_prepopulated_suite()
    return _SUITE_INSTANCE


def reset_context_hook_suite() -> ContextHookPipelineSuite:
    """Reset the singleton instance (primarily for test fixtures)."""
    global _SUITE_INSTANCE
    _SUITE_INSTANCE = _create_prepopulated_suite()
    return _SUITE_INSTANCE
