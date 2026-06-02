"""Kanban completion verifier — hallucination gate.

Implements the harness CompletionVerifier protocol. Determines whether a
task truly completed its stated objective before allowing the dispatcher
to mark it as COMPLETED.

Verification strategy:
1. Task has `metadata["completion_criteria"]` → build ad-hoc LLM semantic judge
2. No criteria configured → skip verification (pass-through)

[INPUT]
- myrm_agent_harness.toolkits.kanban.types::KanbanTask (POS: Domain entity)
- myrm_agent_harness.agent.goals.verification.base::VerificationResult (POS: Result type)

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
from myrm_agent_harness.toolkits.kanban.types import KanbanTask

logger = logging.getLogger(__name__)

_JSON_BLOCK_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)
_JSON_INLINE_RE = re.compile(
    r"\{[^{}]*\"done\"\s*:\s*(?:true|false)[^{}]*\}", re.DOTALL,
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


class KanbanCompletionVerifier:
    """Server-side implementation of the CompletionVerifier protocol.

    Uses the WebUI default model via platform_config for LLM judge calls.
    """

    async def verify(self, task: KanbanTask, result: str) -> VerificationResult:
        """Verify task completion.

        Returns VerificationResult(passed=True) when:
        - Task has no completion_criteria configured (skip verification)
        - LLM judge confirms the task is done
        """
        criteria = self._get_criteria(task)
        if not criteria:
            return VerificationResult(passed=True)

        return await self._judge_completion(task, result, criteria)

    @staticmethod
    def _get_criteria(task: KanbanTask) -> str | None:
        """Extract completion criteria from task metadata."""
        raw = task.metadata.get("completion_criteria")
        if isinstance(raw, str) and raw.strip():
            return raw.strip()
        if isinstance(raw, list) and raw:
            parts = [str(item) for item in raw if item]
            return "; ".join(parts) if parts else None
        return None

    async def _judge_completion(
        self, task: KanbanTask, result: str, criteria: str,
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
                reasoning = getattr(
                    response.choices[0].message, "reasoning_content", None,
                ) or ""
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
            if (
                lower.startswith("pass")
                or '"done": true' in lower
                or '"done":true' in lower
            ):
                return VerificationResult(passed=True, reason=raw)
            return VerificationResult(passed=False, reason=raw)

        except Exception as exc:
            logger.error("Kanban completion verification failed: %s", exc)
            return VerificationResult(
                passed=False,
                reason="Verification judge call failed",
                error_logs=str(exc),
            )
