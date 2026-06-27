"""Daily Wrap API — AI-generated daily activity summary.

Generates a natural language summary, keywords, and suggestions based on
aggregated daily activity data (reusing daily_journal fetchers). Results are
cached in the main SQLite database (one row per date) to minimize LLM costs.

[INPUT]
- app.api.statistics.daily_journal (POS: data fetchers for sessions, approvals, cron runs, kanban)
- app.core.channel_bridge.config_loader (POS: load user LLM configs)
- app.core.channel_bridge.config_parsers (POS: extract lite model config)
- myrm_agent_harness.toolkits.llms (POS: create_litellm_model for LLM calls)

[OUTPUT]
- router: Daily Wrap APIRouter (get_daily_wrap, regenerate_daily_wrap)

[POS]
Daily Wrap API. Provides an AI-generated narrative summary of the day's agent
activity. Low-cost (LITE_MODEL + caching), pure additive (no modification to
existing code), zero impact on prompt cache or agent system.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.statistics.daily_journal import (
    _fetch_approvals,
    _fetch_cron_runs,
    _fetch_kanban_events,
    _fetch_sessions,
    _parse_day,
)
from app.core.utils.errors import StandardHTTPException, internal_error
from app.core.utils.response_utils import success_response
from app.database.connection import get_db
from app.database.models.daily_wrap import DailyWrapCache

router = APIRouter()
logger = logging.getLogger(__name__)


# ── LLM Generation ──────────────────────────────────────────────────


_WRAP_SYSTEM_PROMPT = """\
You are a concise productivity assistant. Given the user's daily activity data, \
generate a brief daily wrap summary in the SAME LANGUAGE as the activity titles \
(if titles are Chinese, respond in Chinese; if English, respond in English).

Return ONLY valid JSON with this structure:
{
  "summary": "2-4 sentence narrative of what was accomplished today",
  "keywords": ["keyword1", "keyword2", "keyword3"],
  "suggestions": ["actionable suggestion for tomorrow"]
}

Rules:
- summary: focus on accomplishments and patterns, not raw numbers
- keywords: 3-5 most relevant topic keywords from today's activities
- suggestions: 1-3 brief, actionable items for the next day based on patterns
- Keep it concise and useful. No filler."""


def _build_activity_prompt(
    date: str,
    sessions: list[dict[str, object]],
    approvals: list[dict[str, object]],
    cron_runs: list[dict[str, object]],
    kanban_events: list[dict[str, object]],
) -> str:
    """Build the user prompt from aggregated activity data."""
    lines = [f"Date: {date}"]
    lines.append(f"Sessions: {len(sessions)}")

    if sessions:
        total_tokens = sum(int(s.get("total_tokens", 0)) for s in sessions)
        total_cost = sum(float(s.get("total_usd", 0)) for s in sessions)
        lines.append(f"Total tokens: {total_tokens:,}")
        lines.append(f"Total cost: ${total_cost:.4f}")
        lines.append("Session titles:")
        for s in sessions[:15]:
            title = str(s.get("title", "Untitled"))
            mode = str(s.get("action_mode", ""))
            lines.append(f"  - {title} ({mode})")

    if approvals:
        lines.append(f"\nApprovals: {len(approvals)}")
        for a in approvals[:5]:
            lines.append(f"  - {a.get('action_type')} [{a.get('status')}]")

    if cron_runs:
        lines.append(f"\nScheduled tasks: {len(cron_runs)}")
        for c in cron_runs[:5]:
            lines.append(f"  - Job {c.get('job_id')} [{c.get('status')}]")

    if kanban_events:
        lines.append(f"\nKanban events: {len(kanban_events)}")
        for k in kanban_events[:5]:
            lines.append(f"  - Task {k.get('task_id')} [{k.get('kind')}]")

    return "\n".join(lines)


async def _generate_wrap_via_llm(
    date: str,
    sessions: list[dict[str, object]],
    approvals: list[dict[str, object]],
    cron_runs: list[dict[str, object]],
    kanban_events: list[dict[str, object]],
) -> dict[str, object] | None:
    """Call LITE_MODEL to generate daily wrap. Returns None if model not configured."""
    from app.core.channel_bridge.config_loader import load_user_configs
    from app.core.channel_bridge.config_parsers import extract_lite_model_config

    configs = await load_user_configs()
    lite_cfg = extract_lite_model_config(configs.providers_dict)
    if not lite_cfg:
        return None

    from myrm_agent_harness.toolkits.llms import create_litellm_model

    llm = create_litellm_model(
        model=lite_cfg.model,
        base_url=lite_cfg.base_url,
        api_key=lite_cfg.api_key,
        temperature=0.3,
        streaming=False,
    )

    user_prompt = _build_activity_prompt(date, sessions, approvals, cron_runs, kanban_events)

    response = await llm.ainvoke(
        [
            SystemMessage(content=_WRAP_SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ],
        config={"max_tokens": 500, "timeout": 15},
    )

    raw = str(response.content).strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1].rsplit("```", 1)[0].strip()

    try:
        parsed = json.loads(raw)
        return {
            "summary": str(parsed.get("summary", "")),
            "keywords": list(parsed.get("keywords", [])),
            "suggestions": list(parsed.get("suggestions", [])),
        }
    except (json.JSONDecodeError, TypeError):
        logger.warning("Daily wrap LLM returned non-JSON: %s", raw[:200])
        return {"summary": raw[:500], "keywords": [], "suggestions": []}


# ── Endpoints ────────────────────────────────────────────────────────


async def _fetch_and_generate(
    db: AsyncSession,
    date: str,
) -> dict[str, object]:
    """Fetch activity data and generate wrap via LLM. Shared by GET/POST endpoints."""
    day_start, day_end = _parse_day(date)

    sessions = await _fetch_sessions(db, day_start, day_end, agent_id=None)
    approvals = await _fetch_approvals(db, day_start, day_end)
    cron_runs = await _fetch_cron_runs(db, day_start, day_end)
    kanban_events = await _fetch_kanban_events(db, day_start, day_end)

    if not sessions and not approvals and not cron_runs and not kanban_events:
        return {
            "date": date,
            "summary": None,
            "keywords": [],
            "suggestions": [],
            "generated_at": None,
            "reason": "no_activity",
        }

    result = await _generate_wrap_via_llm(date, sessions, approvals, cron_runs, kanban_events)
    if result is None:
        return {
            "date": date,
            "summary": None,
            "keywords": [],
            "suggestions": [],
            "generated_at": None,
            "reason": "lite_model_not_configured",
        }

    now = datetime.now(timezone.utc)
    cache_entry = DailyWrapCache(
        date=date,
        summary=result["summary"],
        keywords=json.dumps(result["keywords"], ensure_ascii=False),
        suggestions=json.dumps(result["suggestions"], ensure_ascii=False),
        generated_at=now,
    )
    await db.merge(cache_entry)
    await db.commit()

    return {
        "date": date,
        "summary": result["summary"],
        "keywords": result["keywords"],
        "suggestions": result["suggestions"],
        "generated_at": now.isoformat(),
    }


@router.get("/daily-wrap")
async def get_daily_wrap(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Get cached or freshly generated daily wrap summary.

    Returns cached result if available; otherwise generates via LITE_MODEL.
    If LITE_MODEL is not configured, returns null data with a reason field.
    """
    try:
        cached = await db.execute(select(DailyWrapCache).where(DailyWrapCache.date == date))
        row = cached.scalar_one_or_none()
        if row:
            return success_response(data={
                "date": date,
                "summary": row.summary,
                "keywords": json.loads(row.keywords),
                "suggestions": json.loads(row.suggestions),
                "generated_at": row.generated_at.isoformat() if row.generated_at else None,
                "cached": True,
            })

        data = await _fetch_and_generate(db, date)
        data["cached"] = False
        return success_response(data=data)
    except StandardHTTPException:
        raise
    except Exception as exc:
        raise internal_error(operation="Get daily wrap", exception=exc) from exc


@router.post("/daily-wrap/regenerate")
async def regenerate_daily_wrap(
    date: str = Query(..., description="Date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """Force regenerate daily wrap for a given date (invalidates cache)."""
    try:
        data = await _fetch_and_generate(db, date)
        return success_response(data=data)
    except StandardHTTPException:
        raise
    except Exception as exc:
        raise internal_error(operation="Regenerate daily wrap", exception=exc) from exc
