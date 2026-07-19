"""Goal draft generation — suggest constraints and acceptance criteria from objective.

[INPUT]
- langchain_core.language_models::BaseChatModel (POS: Lite model for structured draft)

[OUTPUT]
- draft_goal_spec: Generate constraints, acceptance_criteria, ui_summary from objective text
- _normalize_draft / _parse_draft_json: Pure helpers for tests

[POS]
Server-side pre-goal helper for GUI users. Output must be previewed and confirmed before
creating a Goal — never silently applied.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel

logger = logging.getLogger(__name__)

_DRAFT_SYSTEM = """You help users define measurable acceptance criteria for autonomous agent goals.
Return ONLY valid JSON with this shape:
{
  "ui_summary": "short label under 120 chars",
  "constraints": ["hard rule 1", "hard rule 2"],
  "acceptance_criteria": [
    {"type": "shell", "command": "pytest -q", "timeout_seconds": 120},
    {"type": "semantic", "criteria": "Report covers all requested sections"}
  ]
}
Rules:
- constraints: things the agent must NOT do (max 5, concise)
- acceptance_criteria: verifiable checks (max 6); prefer shell commands when testable
- shell criteria need "command" and optional timeout_seconds (default 60)
- semantic criteria need "criteria" text
- ui_summary: user-facing short title, no technical jargon
"""


async def draft_goal_spec(
    llm: BaseChatModel,
    objective: str,
    *,
    locale: str | None = None,
) -> dict[str, object]:
    """Generate a draft goal spec from a natural-language objective."""
    objective_clean = " ".join(objective.split()).strip()
    if not objective_clean:
        raise ValueError("Objective must not be empty")

    locale_hint = f"User locale: {locale}. " if locale else ""
    user_prompt = (
        f"{locale_hint}Objective:\n{objective_clean}\n\n"
        "Produce constraints and acceptance_criteria suitable for this goal."
    )

    response = await llm.ainvoke(
        [
            {"role": "system", "content": _DRAFT_SYSTEM},
            {"role": "user", "content": user_prompt},
        ]
    )
    raw = response.content if hasattr(response, "content") else str(response)
    if isinstance(raw, list):
        raw = " ".join(
            block.get("text", "") if isinstance(block, dict) else str(block) for block in raw
        )

    parsed = _parse_draft_json(str(raw))
    return _normalize_draft(parsed, objective_clean)


def _parse_draft_json(text: str) -> dict[str, object]:
    text = text.strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass

    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if fence:
        try:
            data = json.loads(fence.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    brace = re.search(r"\{.*\}", text, re.DOTALL)
    if brace:
        try:
            data = json.loads(brace.group(0))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    logger.warning("Goal draft: failed to parse LLM JSON, using empty draft")
    return {}


def _normalize_draft(data: dict[str, object], objective: str) -> dict[str, object]:
    ui_summary_raw = data.get("ui_summary")
    ui_summary = str(ui_summary_raw).strip() if ui_summary_raw else objective[:120]

    constraints_raw = data.get("constraints")
    constraints: list[str] = []
    if isinstance(constraints_raw, list):
        for item in constraints_raw[:5]:
            text = str(item).strip()
            if text:
                constraints.append(text)

    criteria_raw = data.get("acceptance_criteria")
    acceptance_criteria: list[dict[str, object]] = []
    if isinstance(criteria_raw, list):
        for item in criteria_raw[:6]:
            if not isinstance(item, dict):
                continue
            criterion_type = str(item.get("type", "")).lower()
            if criterion_type == "shell":
                command = str(item.get("command", "")).strip()
                if not command:
                    continue
                timeout = item.get("timeout_seconds", 60)
                try:
                    timeout_int = int(timeout)  # type: ignore[arg-type]
                except (TypeError, ValueError):
                    timeout_int = 60
                acceptance_criteria.append(
                    {"type": "shell", "command": command, "timeout_seconds": max(1, timeout_int)}
                )
            elif criterion_type == "semantic":
                criteria_text = str(item.get("criteria", "")).strip()
                if criteria_text:
                    acceptance_criteria.append({"type": "semantic", "criteria": criteria_text})

    return {
        "ui_summary": ui_summary[:120],
        "constraints": constraints,
        "acceptance_criteria": acceptance_criteria,
    }
