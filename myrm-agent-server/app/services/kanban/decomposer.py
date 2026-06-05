"""Kanban Task Decomposer — TRIAGE → child task graph via WebUI LLM.

Implements the ``TaskDecomposer`` Protocol from the harness layer using the
platform's WebUI-configured LiteLLM model.  Mirrors the design of
``specifier.py``: CJK-aware prompts, lenient JSON parsing, never-raise
contract.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskDecomposer, DecomposeOutcome,
    DecomposeChildSpec (POS: Harness protocol for TRIAGE→child-graph.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskStatus
- app.services.kanban.llm_utils (POS: Shared LLM helpers.)
- app.services.agent.platform_config::build_platform_litellm_kwargs

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

_SYSTEM_PROMPT_EN = """You are the Kanban decomposer for a multi-agent task board.

A user dropped a rough idea into the Triage column. Your job is to break it
into a small graph of concrete child tasks and route each one to the best-
matching agent profile from the available roster.

You will be given:
  - The original task title and body
  - The list of available agent profiles (each with name + description)
  - The fallback "default_assignee" used when no profile fits

Output a single JSON object with this exact shape:

  {
    "fanout": true,
    "rationale": "<one sentence on why this decomposition>",
    "tasks": [
      {
        "title": "<concrete task title, imperative voice, <= 80 chars>",
        "body":  "<detailed spec for the worker on this child task>",
        "assignee": "<agent profile name from the roster, or null for default>",
        "parents": [<int>, ...]
      },
      ...
    ]
  }

Rules:
  - "parents" is a list of INDICES (0-based) into this same "tasks" list,
    expressing actual data dependencies. Tasks with no parents run in
    PARALLEL. Tasks with parents wait until every parent completes.
  - Prefer parallelism. If two tasks can be done independently, give
    them no parents so the dispatcher fans them out at once.
  - Use 2-6 tasks for normal work. Don't create 20 tiny tasks. Don't
    cram everything into 1 task.
  - Pick assignees from the roster by matching the task to the profile's
    DESCRIPTION (not just the name). When nothing matches well, use null
    and the system will route to the default_assignee.
  - Each child task body is what a fresh worker will read with no other
    context — be specific about goal, approach, and acceptance criteria.

When the task is genuinely a single unit of work (no useful decomposition),
return a single-task spec instead (same effect as "specify"):

  {
    "fanout": false,
    "rationale": "<one sentence>",
    "title": "<tightened title, imperative voice, <= 80 chars>",
    "body":  "<concrete spec: Goal / Approach / Acceptance criteria / Out-of-scope>",
    "assignee": "<profile name from the roster, or null for default>"
  }

No preamble, no closing remarks, no code fences. Output only the JSON object.
"""

_SYSTEM_PROMPT_ZH = """你是多智能体看板的任务分解器 (Kanban Decomposer)。

用户在 Triage 列丢入了一个粗略想法。你的工作是将其拆分为多个具体的子任务，
并将每个子任务路由到最匹配的智能体。

你会收到：
  - 原始任务标题和描述
  - 可用智能体列表（每个含名称+描述）
  - 默认 assignee（当没有合适的智能体时使用）

输出一个 JSON 对象：

  {
    "fanout": true,
    "rationale": "<一句话说明为何这样拆分>",
    "tasks": [
      {
        "title": "<具体任务标题, 祈使语气, <= 80 字符>",
        "body":  "<详细的子任务规范>",
        "assignee": "<智能体名称, 或 null 使用默认>",
        "parents": [<int>, ...]
      }
    ]
  }

规则：
  - "parents" 是索引列表（0 起始），表示数据依赖。空 parents 的任务并行执行。
  - 优先并行。两个独立的任务不要设置依赖。
  - 2-6 个子任务为宜。不要创建 20 个碎片任务，也不要塞进 1 个。
  - 按智能体描述匹配，不匹配则 assignee 设为 null。
  - 每个子任务 body 要完整，让全新的 worker 无需其他上下文即可执行。

如果任务是不可拆分的单体工作，返回规范化后的单任务（等同于 specify）：

  {
    "fanout": false,
    "rationale": "<一句话>",
    "title": "<精炼的标题, 祈使语气, <= 80 字符>",
    "body":  "<具体规范: 目标 / 方案 / 验收条件 / 范围外>",
    "assignee": "<智能体名称, 或 null 使用默认>"
  }

不要前言、结语、代码围栏，只输出 JSON。
"""

_USER_TEMPLATE = """Task id: {task_id}
Title: {title}
Body:
{body}

Available agent profiles (assignees you may pick from):
{roster}

Default assignee (used when no profile fits): {default_assignee}
"""


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
            logger.info("decompose: platform LLM unavailable for %s: %s", task.task_id[:8], exc)
            return DecomposeOutcome(
                task_id=task.task_id,
                ok=False,
                reason="decomposer_unavailable",
            )

        system_prompt = _SYSTEM_PROMPT_ZH if has_cjk(task.title) or has_cjk(task.description) else _SYSTEM_PROMPT_EN
        user_msg = _USER_TEMPLATE.format(
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
            raw_content = response.choices[0].message.content or ""
            raw = str(raw_content).strip()
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
            new_title = new_title_raw.strip()[:200] if isinstance(new_title_raw, str) and new_title_raw.strip() else None
            new_body_raw = parsed.get("body")
            new_body = new_body_raw.strip() if isinstance(new_body_raw, str) and new_body_raw.strip() else None
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
            clean_parents = tuple(p for p in parents_raw if isinstance(p, int) and 0 <= p < len(raw_tasks) and p != idx)
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
