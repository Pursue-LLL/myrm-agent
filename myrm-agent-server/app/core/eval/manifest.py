"""Eval manifest building — environment snapshot captured per run.

[INPUT]
- myrm_agent_harness.eval::EvalManifest
- app.core.eval.model_config::_resolve_agent_model_label (POS: 统一模型解析，profile 声明优先、兜底 model_cfg)

[OUTPUT]
- _build_eval_manifest: builds an EvalManifest snapshot of the current run.

[POS]
构建评测环境快照（模型/引擎参数/tool policy/提示词指纹/任务集哈希/抽样），
供报告展示、可复现性追溯与诚实披露（sampled、judge_model、agent_model）。
"""

from __future__ import annotations

import hashlib
import pickle
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import myrm_agent_harness
from myrm_agent_harness.eval import EvalManifest

from app.core.eval.model_config import _resolve_agent_model_label

if TYPE_CHECKING:
    from myrm_agent_harness.eval import MultiTurnEvalCase


async def _build_eval_manifest(
    profile_id: str | None,
    dataset_id: str,
    cases_path: Path,
    *,
    benchmark_mode: bool = False,
    external_cases: list["MultiTurnEvalCase"] | None = None,
    judge_model: str = "none",
    limit: int | None = None,
    max_tool_calls: int | None = None,
    max_iterations: int | None = None,
) -> EvalManifest:
    """Build an EvalManifest capturing the current evaluation environment."""
    model_provider = "unknown"
    model_id = "unknown"
    budget_max_tokens = 4096
    thinking_effort = "default"
    tool_policy: list[str] = []
    prompt_fingerprint = "none"

    if profile_id:
        from app.services.agent.profile.profile_resolver import (
            get_agent_profile_resolver,
        )

        resolved = await get_agent_profile_resolver().resolve(profile_id)
        if resolved:
            if resolved.model:
                parts = resolved.model.split("/", 1)
                if len(parts) == 2:
                    model_provider, model_id = parts
                else:
                    model_id = resolved.model
            if resolved.engine_params:
                thinking_effort = str(
                    resolved.engine_params.get("thinking_effort", "default")
                )
                max_tokens_value = resolved.engine_params.get(
                    "max_tokens", budget_max_tokens
                )
                if isinstance(max_tokens_value, int):
                    budget_max_tokens = max_tokens_value
                elif isinstance(max_tokens_value, str) and max_tokens_value.isdigit():
                    budget_max_tokens = int(max_tokens_value)
            tool_policy = list(resolved.enabled_builtin_tools)
            if resolved.system_prompt:
                prompt_fingerprint = hashlib.sha256(
                    resolved.system_prompt.encode("utf-8")
                ).hexdigest()

    if model_id == "unknown":
        # Model not declared by the profile (or no profile selected): fall
        # back through the shared resolver so the manifest and the Memory A/B
        # report disclose the identical agent-model label.
        fallback_label = await _resolve_agent_model_label(profile_id)
        parts = fallback_label.split("/", 1)
        if len(parts) == 2:
            model_provider, model_id = parts
        else:
            model_id = fallback_label

    task_set_hash = "empty"
    if cases_path.exists():
        content = cases_path.read_bytes()
        task_set_hash = hashlib.sha256(content).hexdigest()
    else:
        try:
            task_set_hash = hashlib.sha256(pickle.dumps(external_cases)).hexdigest()
        except (
            Exception
        ):  # noqa: BLE001 - fall back to a stable marker on any serialization edge case
            task_set_hash = f"external-{dataset_id}"

    return EvalManifest(
        model_provider=model_provider,
        model_id=model_id,
        thinking_effort=thinking_effort,
        harness_version=myrm_agent_harness.__version__,
        tool_policy=tuple(tool_policy),
        task_set_id=dataset_id,
        task_set_hash=task_set_hash,
        prompt_fingerprint=prompt_fingerprint,
        budget_max_tokens=budget_max_tokens,
        timeout_seconds=300,
        created_at=datetime.now(timezone.utc).isoformat(),
        profile_id=profile_id or "default",
        benchmark_mode=benchmark_mode,
        judge_model=judge_model,
        limit=limit,
        max_tool_calls=max_tool_calls,
        max_iterations=max_iterations,
    )
