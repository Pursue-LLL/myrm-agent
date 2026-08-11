"""Kanban Task Decomposer — TRIAGE → child task graph via WebUI LLM.

Implements the ``TaskDecomposer`` Protocol from the harness layer using the
platform's WebUI-configured LiteLLM model.  Mirrors the design of
``specify.specifier``: CJK-aware prompts, lenient JSON parsing, never-raise
contract.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskDecomposer, DecomposeOutcome,
    DecomposeChildSpec (POS: Harness protocol for TRIAGE→child-graph.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskStatus
- app.services.kanban.llm_utils (POS: Shared LLM helpers.)
- app.services.agent.platform_config::build_platform_litellm_kwargs
- app.core.utils.chat_utils::extract_litellm_answer_text (POS: litellm 响应文本提取)

[OUTPUT]
- PlatformTaskDecomposer: Concrete TaskDecomposer using LiteLLM + WebUI config.

[POS]
Server-layer TaskDecomposer that bridges TRIAGE decomposition to the platform LLM.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.kanban.protocols import (
    DecomposeChildSpec,
    DecomposeOutcome,
)
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.core.utils.chat_utils import extract_litellm_answer_text
from app.services.kanban.decompose.prompts import (
    SYSTEM_PROMPT_EN,
    SYSTEM_PROMPT_ZH,
    USER_TEMPLATE,
)
from app.services.kanban.llm_utils import (
    extract_json_blob,
    extract_usage,
    has_cjk,
    truncate,
)

logger = logging.getLogger(__name__)

DEFAULT_DECOMPOSE_TIMEOUT_SECONDS: int = 180

_MAX_TITLE_FORWARD = 400
_MAX_BODY_FORWARD = 4000


def _format_roster(roster: list[dict[str, str]]) -> str:
    if not roster:
        return "  (no agent profiles installed)"
    lines: list[str] = []
    for entry in roster:
        desc = entry.get("description", "")
        tag = "" if desc else " [no description]"
        lines.append(f"  - {entry['name']}{tag}: {desc or entry['name']}")
    return "\n".join(lines)


def _normalize_assignee(
    assignee: object,
    *,
    default_assignee: str,
    valid_names: set[str],
) -> str:
    """Return a valid assignee, falling back to *default_assignee*."""
    if not isinstance(assignee, str) or not assignee.strip():
        return default_assignee
    chosen = assignee.strip()
    if chosen not in valid_names:
        logger.info(
            "LLM proposed invalid assignee %r (valid: %s) — falling back to %r",
            chosen,
            ", ".join(sorted(valid_names)),
            default_assignee,
        )
        return default_assignee
    return chosen


class PlatformTaskDecomposer:
    """Concrete TaskDecomposer using the WebUI-configured platform LLM.

    Never raises for expected failures — all such cases surface via
    ``DecomposeOutcome(ok=False, reason=…)``.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 4000,
        timeout_seconds: int = DEFAULT_DECOMPOSE_TIMEOUT_SECONDS,
        temperature: float = 0.3,
    ) -> None:
        self._max_tokens = max(1500, max_tokens)
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature

    async def decompose(
        self,
        task: KanbanTask,
        *,
        roster: list[dict[str, str]],
        default_assignee: str,
    ) -> DecomposeOutcome:
        if task.status != TaskStatus.TRIAGE:
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=False,
                reason="not_triage",
            )

        try:
            from app.services.agent.platform_config import build_platform_litellm_kwargs

            llm_kwargs = await build_platform_litellm_kwargs()
        except Exception as exc:
            logger.info(
                "decompose: platform LLM unavailable for %s: %s", task.task_id[:8], exc
            )
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=False,
                reason="decomposer_unavailable",
            )

        system_prompt = (
            SYSTEM_PROMPT_ZH
            if has_cjk(task.title) or has_cjk(task.description)
            else SYSTEM_PROMPT_EN
        )
        user_msg = USER_TEMPLATE.format(
            task_id=task.task_id,
            title=truncate(task.title or "", _MAX_TITLE_FORWARD),
            body=truncate(task.description or "(no body)", _MAX_BODY_FORWARD),
            roster=_format_roster(roster),
            default_assignee=default_assignee,
        )

        try:
            import litellm

            response = await litellm.acompletion(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg},
                ],
                temperature=self._temperature,
                max_tokens=self._max_tokens,
                timeout=self._timeout_seconds,
                **llm_kwargs,
            )
        except Exception as exc:
            logger.info("decompose: LLM call failed for %s: %s", task.task_id[:8], exc)
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=False,
                reason=f"llm_error:{type(exc).__name__}",
            )

        prompt_tokens, completion_tokens = extract_usage(response)

        try:
            # 兼容 Anthropic 块列表 / reasoning 模型 content 空回退
            raw = extract_litellm_answer_text(response).strip()
        except Exception:
            raw = ""

        parsed = extract_json_blob(raw)
        if parsed is None:
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=False,
                reason="parse_failed",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        fanout = bool(parsed.get("fanout"))
        rationale = str(parsed.get("rationale", ""))
        valid_names = {e["name"] for e in roster}

        if not fanout:
            new_title_raw = parsed.get("title")
            new_title = (
                new_title_raw.strip()[:200]
                if isinstance(new_title_raw, str) and new_title_raw.strip()
                else None
            )
            new_body_raw = parsed.get("body")
            new_body = (
                new_body_raw.strip()
                if isinstance(new_body_raw, str) and new_body_raw.strip()
                else None
            )
            new_assignee_raw = parsed.get("assignee")
            new_assignee = (
                _normalize_assignee(
                    new_assignee_raw,
                    default_assignee=default_assignee,
                    valid_names=valid_names,
                )
                if isinstance(new_assignee_raw, str) and new_assignee_raw.strip()
                else None
            )
            if new_title is None and new_body is None:
                return DecomposeOutcome(
                    task_id=task.task_id,
                    ok=False,
                    reason="no_fanout_empty_result",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=True,
                fanout=False,
                rationale=rationale,
                reason="no_fanout",
                new_title=new_title,
                new_body=new_body,
                new_assignee=new_assignee,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        raw_tasks = parsed.get("tasks") or []
        if not isinstance(raw_tasks, list) or not raw_tasks:
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=False,
                reason="empty_tasks_list",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )

        children: list[DecomposeChildSpec] = []

        for idx, entry in enumerate(raw_tasks):
            if not isinstance(entry, dict):
                return DecomposeOutcome(
                    task_id=task.task_id,
                    ok=False,
                    reason=f"tasks[{idx}]_not_object",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            title = entry.get("title")
            if not isinstance(title, str) or not title.strip():
                return DecomposeOutcome(
                    task_id=task.task_id,
                    ok=False,
                    reason=f"tasks[{idx}]_missing_title",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                )
            body = entry.get("body")
            if not isinstance(body, str):
                body = ""
            assignee = _normalize_assignee(
                entry.get("assignee"),
                default_assignee=default_assignee,
                valid_names=valid_names,
            )
            parents_raw = entry.get("parents") or []
            if not isinstance(parents_raw, list):
                parents_raw = []
            clean_parents = tuple(
                p
                for p in parents_raw
                if isinstance(p, int) and 0 <= p < len(raw_tasks) and p != idx
            )
            children.append(
                DecomposeChildSpec(
                    title=title.strip()[:200],
                    body=body.strip(),
                    assignee=assignee,
                    parent_indices=clean_parents,
                )
            )

        return DecomposeOutcome(
            task_id=task.task_id,
            ok=True,
            fanout=True,
            children=tuple(children),
            rationale=rationale,
            reason="decomposed",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
        )
