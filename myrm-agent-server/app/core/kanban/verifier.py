"""Kanban completion verifier — hallucination gate.

Implements the harness CompletionVerifier protocol. Determines whether a
task truly completed its stated objective before allowing the dispatcher
to mark it as COMPLETED.

Verification strategy (layered):
1. No criteria configured → skip verification (pass-through)
2. Structured criteria list → execute shell + semantic criteria in order
   - Shell criteria run first (zero LLM cost, objective check)
   - Any shell failure → immediate reject (skip semantic)
   - Semantic criteria → LLM judge (only if all shell criteria pass)
3. Plain-text criteria → LLM semantic judge only

[INPUT]
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Domain entity)
- myrm_agent_harness.agent.goals.verification.base::VerificationResult (POS: Result type)
- myrm_agent_harness.agent.goals.verification.shell::ShellCriterion (POS: Sandbox shell verifier)

[OUTPUT]
- KanbanCompletionVerifier: Server-side CompletionVerifier implementation.

[POS]
Kanban completion verifier — hallucination gate.
"""

from __future__ import annotations

import json
import logging
import re

from myrm_agent_harness.agent.goals.verification.base import VerificationResult
from myrm_agent_harness.agent.goals.verification.shell import ShellCriterion
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_INLINE_RE = re.compile(
    r"\{[^{}]*\"done\"\s*:\s*(?:true|false)[^{}]*\}",
    re.DOTALL,
)


def _parse_judge_json(raw: str) -> dict[str, object] | None:
    """Extract {"done": bool, "reason": str} from LLM judge output."""
    try:
        obj = json.loads(raw)
        if isinstance(obj, dict) and "done" in obj:
            return _normalize_done(obj)
    except (json.JSONDecodeError, ValueError):
        pass

    m = _JSON_BLOCK_RE.search(raw)
    if m:
        try:
            obj = json.loads(m.group(1))
            if isinstance(obj, dict) and "done" in obj:
                return _normalize_done(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    m = _JSON_INLINE_RE.search(raw)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict) and "done" in obj:
                return _normalize_done(obj)
        except (json.JSONDecodeError, ValueError):
            pass

    return None


def _normalize_done(obj: dict[str, object]) -> dict[str, object]:
    done = obj.get("done")
    if isinstance(done, str):
        obj["done"] = done.strip().lower() in ("true", "yes", "1")
    return obj


def _parse_criteria(
    raw: object,
) -> tuple[list[dict[str, object]], list[str]]:
    """Parse completion_criteria into (shell_configs, semantic_texts).

    Supports two formats:
    - Plain string: treated as a single semantic criterion
    - Structured list: ``[{"type": "shell", "command": "..."}, {"type": "semantic", "criteria": "..."}]``
    """
    if isinstance(raw, str) and raw.strip():
        return [], [raw.strip()]

    if not isinstance(raw, list) or not raw:
        return [], []

    shell_configs: list[dict[str, object]] = []
    semantic_texts: list[str] = []

    for item in raw:
        if isinstance(item, str):
            if item.strip():
                semantic_texts.append(item.strip())
            continue
        if not isinstance(item, dict):
            continue
        crit_type = item.get("type", "")
        if crit_type == "shell":
            command = item.get("command")
            if isinstance(command, str) and command.strip():
                shell_configs.append(item)
        elif crit_type == "semantic":
            criteria = item.get("criteria")
            if isinstance(criteria, str) and criteria.strip():
                semantic_texts.append(criteria.strip())

    return shell_configs, semantic_texts


class KanbanCompletionVerifier:
    """Server-side implementation of the CompletionVerifier protocol.

    Layered verification: shell criteria first (objective, zero LLM cost),
    then semantic criteria (LLM judge) only when shell criteria all pass.
    """

    async def verify(self, task: KanbanTask, result: str) -> VerificationResult:
        """Verify task completion with layered shell + semantic strategy."""
        raw = task.metadata.get("completion_criteria")
        if raw is None:
            return VerificationResult(passed=True)

        shell_configs, semantic_texts = _parse_criteria(raw)
        if not shell_configs and not semantic_texts:
            return VerificationResult(passed=True)

        shell_failure = await self._run_shell_criteria(shell_configs)
        if shell_failure is not None:
            return shell_failure

        if semantic_texts:
            combined = "; ".join(semantic_texts)
            return await self._judge_completion(task, result, combined)

        return VerificationResult(passed=True)

    async def _run_shell_criteria(
        self,
        configs: list[dict[str, object]],
    ) -> VerificationResult | None:
        """Execute shell criteria in order. Returns first failure or None."""
        for cfg in configs:
            command = str(cfg.get("command", ""))
            try:
                timeout = int(cfg.get("timeout_seconds", 60))
            except (TypeError, ValueError):
                timeout = 60
            criterion = ShellCriterion(command=command, timeout_seconds=timeout)
            vr = await criterion.verify()
            if not vr.passed:
                return VerificationResult(
                    passed=False,
                    reason=f"Shell verification failed: {command}",
                    error_logs=vr.error_logs,
                )
        return None

    async def _judge_completion(
        self,
        task: KanbanTask,
        result: str,
        criteria: str,
    ) -> VerificationResult:
        """Run LLM judge to verify completion against criteria."""
        from litellm import acompletion

        from app.services.agent.platform_config import build_platform_litellm_kwargs

        system_prompt = (
            "You are a strict judge evaluating whether an autonomous agent has "
            "truly completed a task according to specific acceptance criteria.\n\n"
            f"Task: {task.title}\n"
            f"Description: {task.description or '(none)'}\n\n"
            f"Acceptance criteria:\n{criteria}\n\n"
            "Judge whether the agent's result satisfies ALL acceptance criteria.\n"
            "Reply ONLY with JSON: "
            '{"done": true/false, "reason": "one-sentence rationale"}'
        )
        user_content = f"Agent's result:\n{result[:3000]}"

        try:
            llm_kwargs = await build_platform_litellm_kwargs()
            response = await acompletion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_content},
                ],
                temperature=0.0,
                max_tokens=256,
                timeout=30,
                **llm_kwargs,
            )
            raw = (response.choices[0].message.content or "").strip()

            if not raw:
                reasoning = (
                    getattr(
                        response.choices[0].message,
                        "reasoning_content",
                        None,
                    )
                    or ""
                )
                if reasoning:
                    raw = reasoning.strip()

            parsed = _parse_judge_json(raw)
            if parsed is not None:
                done = parsed.get("done", False)
                reason = str(parsed.get("reason", ""))
                if done:
                    return VerificationResult(passed=True, reason=reason)
                return VerificationResult(passed=False, reason=reason)

            lower = raw.lower()
            is_pass = (
                lower.startswith("pass")
                or '"done": true' in lower
                or '"done":true' in lower
            )
            if is_pass:
                return VerificationResult(passed=True, reason=raw)
            return VerificationResult(passed=False, reason=raw)

        except Exception as exc:
            logger.error("Kanban completion verification failed: %s", exc)
            return VerificationResult(
                passed=False,
                reason="Verification judge call failed",
                error_logs=str(exc),
            )
