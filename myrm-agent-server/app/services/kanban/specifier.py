"""Kanban Task Specifier — TRIAGE one-liner → structured spec via WebUI LLM.

Implements the ``TaskSpecifier`` Protocol from the harness layer using the
platform's WebUI-configured LiteLLM model (``build_platform_litellm_kwargs``),
so there's no second-set-of-credentials surface and no env fallback.

[INPUT]
- myrm_agent_harness.toolkits.kanban.protocols::TaskSpecifier, SpecifyOutcome
    (POS: Harness protocol for TRIAGE→spec rewrite.)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask, TaskStatus
- app.services.agent.platform_config::build_platform_litellm_kwargs
    (POS: WebUI-configured LLM kwargs, no env fallback.)

[OUTPUT]
- PlatformTaskSpecifier: Concrete TaskSpecifier using LiteLLM + WebUI config.
- DEFAULT_SPECIFY_TIMEOUT_SECONDS: Module-level constant.

[POS]
Server-layer TaskSpecifier that bridges TRIAGE rewrites to the platform LLM.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.kanban.protocols import SpecifyOutcome
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskStatus

from app.services.kanban.llm_utils import extract_json_blob, extract_usage, has_cjk, truncate

logger = logging.getLogger(__name__)


DEFAULT_SPECIFY_TIMEOUT_SECONDS: int = 120


_SYSTEM_PROMPT_EN = """You are the Kanban triage specifier.
A user dropped a rough idea into the Triage column. Turn it into a concrete,
actionable task spec an autonomous worker can pick up and execute without
further clarification.

Output a single JSON object with exactly two keys:

  {
    "title": "<tightened task title, <= 80 chars, imperative voice>",
    "body":  "<multi-line spec, see structure below>"
  }

The body MUST include these sections, each prefixed with a bold markdown
heading, in this order:

  **Goal** — one sentence, user-facing outcome.
  **Approach** — 2-5 bullets on how a worker should tackle it.
  **Acceptance criteria** — checklist of concrete, verifiable conditions
      (each line starts with "- [ ]").
  **Out of scope** — short list of things NOT to touch (omit if nothing
      obvious; never invent scope creep).

Rules:
  - Keep the tightened title close in meaning to the original idea — do
    NOT invent a different project.
  - If the original idea is already detailed, preserve its substance and
    just reformat into the sections above.
  - Never add invented requirements the user didn't hint at.
  - No preamble, no closing remarks, no code fences around the JSON.
  - Output only the JSON object and nothing else.
"""

_SYSTEM_PROMPT_ZH = """你是看板任务规范化助手 (Kanban Triage Specifier)。
用户在 Triage 列丢入了一个粗略想法。请将其改写为一个无需进一步澄清、
独立工作者即可拿起执行的可落地任务规范。

仅输出一个 JSON 对象，必须包含且仅包含两个键：

  {
    "title": "<精炼后的任务标题, <= 80 字符, 使用祈使语气>",
    "body":  "<多行规范，结构见下>"
  }

body 必须依次包含下列章节，每节以加粗 Markdown 标题开头：

  **Goal** — 一句话，描述面向用户的最终结果。
  **Approach** — 2-5 条要点，说明工作者如何落地。
  **Acceptance criteria** — 可逐条核验的清单（每行以 "- [ ]" 开头）。
  **Out of scope** — 不应触碰的范围；若无明显需要说明，可省略。

约束：
  - 精炼后的标题必须贴近原始想法的语义，不得替换为别的项目。
  - 若原始想法已经详细，请保留实质，只按上述结构重排版。
  - 严禁臆造用户未暗示的新需求。
  - 不要前言、结语、代码围栏，**只输出 JSON 对象**。
"""


_USER_TEMPLATE = """Task id: {task_id}
Current title: {title}
Current body:
{body}
"""

_MAX_TITLE_FORWARD = 400
_MAX_BODY_FORWARD = 4000


class PlatformTaskSpecifier:
    """Concrete TaskSpecifier using the WebUI-configured platform LLM.

    Cost control: ``max_tokens`` is hard-clamped at the dispatcher entry to
    ``BoardSettings.specify_max_tokens`` to keep a single triage rewrite
    from blowing the user's monthly budget.

    Failure mode: never raises for expected failures (LLM unavailable,
    network error, malformed reply). All such cases surface via
    ``SpecifyOutcome(ok=False, reason=…)`` so batch sweeps continue past
    a single bad task and the UI can show a clean retry prompt.
    """

    def __init__(
        self,
        *,
        max_tokens: int = 6000,
        timeout_seconds: int = DEFAULT_SPECIFY_TIMEOUT_SECONDS,
        temperature: float = 0.3,
    ) -> None:
        self._max_tokens = max(1500, max_tokens)
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature

    async def specify(
        self,
        task: KanbanTask,
        *,
        persist: bool = False,
    ) -> SpecifyOutcome:
        if task.status != TaskStatus.TRIAGE:
            return SpecifyOutcome(
                task_id=task.task_id,
                ok=False,
                reason="not_triage",
                persisted=False,
            )

        try:
            from app.services.agent.platform_config import build_platform_litellm_kwargs

            llm_kwargs = await build_platform_litellm_kwargs()
        except Exception as exc:
            logger.info(
                "specify: platform LLM kwargs unavailable for %s: %s",
                task.task_id[:8],
                exc,
            )
            return SpecifyOutcome(
                task_id=task.task_id,
                ok=False,
                reason="specifier_unavailable",
                persisted=False,
            )

        system_prompt = (
            _SYSTEM_PROMPT_ZH
            if has_cjk(task.title) or has_cjk(task.description)
            else _SYSTEM_PROMPT_EN
        )
        user_msg = _USER_TEMPLATE.format(
            task_id=task.task_id,
            title=truncate(task.title or "", _MAX_TITLE_FORWARD),
            body=truncate(task.description or "(no body)", _MAX_BODY_FORWARD),
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
            logger.info(
                "specify: LLM call failed for %s: %s",
                task.task_id[:8],
                exc,
            )
            return SpecifyOutcome(
                task_id=task.task_id,
                ok=False,
                reason=f"llm_error:{type(exc).__name__}",
                persisted=False,
            )

        prompt_tokens, completion_tokens = extract_usage(response)

        try:
            raw_content = response.choices[0].message.content or ""
            raw = str(raw_content).strip()
        except Exception:
            raw = ""

        parsed = extract_json_blob(raw)
        if parsed is None:
            stripped_raw = raw.strip()
            if not stripped_raw:
                return SpecifyOutcome(
                    task_id=task.task_id,
                    ok=False,
                    reason="empty_response",
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    persisted=False,
                )
            return SpecifyOutcome(
                task_id=task.task_id,
                ok=True,
                reason="parse_failed_fallback",
                new_title=None,
                new_body=stripped_raw,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                persisted=False,
            )

        title_val = parsed.get("title")
        body_val = parsed.get("body")
        new_title = (
            title_val.strip()
            if isinstance(title_val, str) and title_val.strip()
            else None
        )
        new_body = body_val if isinstance(body_val, str) and body_val.strip() else None

        if new_title is None and new_body is None:
            return SpecifyOutcome(
                task_id=task.task_id,
                ok=False,
                reason="missing_title_and_body",
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                persisted=False,
            )

        return SpecifyOutcome(
            task_id=task.task_id,
            ok=True,
            reason="specified",
            new_title=new_title,
            new_body=new_body,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            persisted=False,
        )


