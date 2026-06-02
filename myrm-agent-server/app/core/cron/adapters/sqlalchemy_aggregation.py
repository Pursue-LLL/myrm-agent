"""Token usage aggregation queries for cron runs.

Application-layer extension beyond the CronStore protocol —
provides analytics grouped by day, job, and model.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TypedDict, cast

from sqlalchemy import case, literal, select
from sqlalchemy.sql import func as sqlfunc

from app.database.connection import get_session
from app.database.models import CronJobModel, CronRunModel


class _SummaryDict(TypedDict):
    total_runs: int
    success_runs: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_tokens_per_run: int


class _ByDayDict(TypedDict):
    date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    runs: int


class _ByJobDict(TypedDict):
    job_id: str
    job_name: str
    total_tokens: int
    runs: int


class _ByModelDict(TypedDict):
    model: str
    total_tokens: int
    runs: int


class UsageAggregateResult(TypedDict):
    summary: _SummaryDict
    by_day: list[_ByDayDict]
    by_job: list[_ByJobDict]
    by_model: list[_ByModelDict]


async def aggregate_usage(
    user_id: str,
    *,
    days: int | None = 7,
) -> UsageAggregateResult:
    """Aggregate token usage across runs for a user's jobs.

    Returns dict with keys: summary, by_day, by_job, by_model.
    """
    async with get_session() as session:
        job_ids_stmt = select(CronJobModel.id)
        cutoff = datetime.now(timezone.utc) - timedelta(days=days) if days else None
        time_filter = [CronRunModel.started_at >= cutoff] if cutoff else []

        summary_stmt = select(
            sqlfunc.count().label("total_runs"),
            sqlfunc.sum(case((CronRunModel.status == "ok", 1), else_=0)).label("success_runs"),
            sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_input_tokens), 0).label("input_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_output_tokens), 0).label("output_tokens"),
            sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_total_tokens), 0).label("total_tokens"),
        ).where(
            CronRunModel.job_id.in_(job_ids_stmt),
            *time_filter,
        )
        row = (await session.execute(summary_stmt)).one()
        total_runs = row.total_runs or 0
        summary: _SummaryDict = {
            "total_runs": int(total_runs),
            "success_runs": int(row.success_runs or 0),
            "total_input_tokens": int(row.input_tokens),
            "total_output_tokens": int(row.output_tokens),
            "total_tokens": int(row.total_tokens),
            "avg_tokens_per_run": int(row.total_tokens) // int(total_runs) if int(total_runs) > 0 else 0,
        }

        by_day_stmt = (
            select(
                sqlfunc.date(CronRunModel.started_at).label("date"),
                sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_input_tokens), 0).label("input_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_output_tokens), 0).label("output_tokens"),
                sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_total_tokens), 0).label("total_tokens"),
                sqlfunc.count().label("runs"),
            )
            .where(
                CronRunModel.job_id.in_(job_ids_stmt),
                *time_filter,
            )
            .group_by(sqlfunc.date(CronRunModel.started_at))
            .order_by(sqlfunc.date(CronRunModel.started_at))
        )
        by_day: list[_ByDayDict] = [
            {
                "date": str(r.date),
                "input_tokens": int(r.input_tokens),
                "output_tokens": int(r.output_tokens),
                "total_tokens": int(r.total_tokens),
                "runs": int(r.runs),
            }
            for r in (await session.execute(by_day_stmt)).all()
        ]

        by_job_stmt = (
            select(
                CronRunModel.job_id,
                sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_total_tokens), 0).label("total_tokens"),
                sqlfunc.count().label("runs"),
            )
            .where(
                CronRunModel.job_id.in_(job_ids_stmt),
                *time_filter,
            )
            .group_by(CronRunModel.job_id)
            .order_by(sqlfunc.sum(CronRunModel.usage_total_tokens).desc())
        )
        by_job_rows = (await session.execute(by_job_stmt)).all()

        job_names: dict[str, str] = {}
        if by_job_rows:
            ids = [r.job_id for r in by_job_rows]
            name_rows = (await session.execute(select(CronJobModel.id, CronJobModel.name).where(CronJobModel.id.in_(ids)))).all()
            job_names = {r.id: r.name for r in name_rows}

        by_job: list[_ByJobDict] = [
            {
                "job_id": r.job_id,
                "job_name": job_names.get(r.job_id, ""),
                "total_tokens": int(r.total_tokens),
                "runs": int(r.runs),
            }
            for r in by_job_rows
        ]

        by_model_stmt = (
            select(
                sqlfunc.coalesce(CronRunModel.model, literal("unknown")).label("model"),
                sqlfunc.coalesce(sqlfunc.sum(CronRunModel.usage_total_tokens), 0).label("total_tokens"),
                sqlfunc.count().label("runs"),
            )
            .where(
                CronRunModel.job_id.in_(job_ids_stmt),
                *time_filter,
            )
            .group_by(sqlfunc.coalesce(CronRunModel.model, literal("unknown")))
            .order_by(sqlfunc.sum(CronRunModel.usage_total_tokens).desc())
        )
        by_model: list[_ByModelDict] = [
            {"model": str(r.model), "total_tokens": int(r.total_tokens), "runs": int(r.runs)}
            for r in (await session.execute(by_model_stmt)).all()
        ]

        return cast(
            UsageAggregateResult,
            {
                "summary": summary,
                "by_day": by_day,
                "by_job": by_job,
                "by_model": by_model,
            },
        )
