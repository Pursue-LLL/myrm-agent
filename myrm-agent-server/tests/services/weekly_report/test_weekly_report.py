"""Unit tests for weekly report SOP and trajectory aggregation service.

Verifies natural week windowing, trajectory extraction, role-adaptive rendering, and wiki dedup.
"""

from __future__ import annotations

import time

from app.channels.delegation.delegation_models import (
    DelegationStatus,
    DelegationTask,
    DeliveryArtifact,
)
from app.services.weekly_report.models import (
    ReportRoleMode,
    WikiIngestPayload,
)
from app.services.weekly_report.trajectory_aggregator import TrajectoryAggregator
from app.services.weekly_report.weekly_report_service import (
    WeeklyReportSOPService,
    WikiIngestionService,
)


def test_natural_week_window() -> None:
    """Verifies natural week window calculation covers 7 days starting from Monday."""
    start_ms, end_ms = TrajectoryAggregator.get_natural_week_window()
    assert start_ms < end_ms
    diff_days = (end_ms - start_ms) / (86400 * 1000)
    assert 6.99 < diff_days <= 7.0


def test_trajectory_aggregation_from_delegation() -> None:
    """Verifies tasks and artifacts are correctly filtered and aggregated."""
    now_ms = int(time.time() * 1000)
    start_ms = now_ms - (3 * 86400 * 1000)
    end_ms = now_ms + (3 * 86400 * 1000)

    task_1 = DelegationTask(
        task_id="task-101",
        session_id="session-1",
        channel_id="feishu",
        instruction="Deploy production microservice",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
        status=DelegationStatus.SUCCEEDED,
        execution_summary="Microservice deployed on port 8080",
    )
    task_out_of_range = DelegationTask(
        task_id="task-102",
        session_id="session-1",
        channel_id="feishu",
        instruction="Old task",
        created_at_ms=now_ms - (10 * 86400 * 1000),
        updated_at_ms=now_ms - (10 * 86400 * 1000),
        status=DelegationStatus.SUCCEEDED,
    )
    art_1 = DeliveryArtifact(
        artifact_id="art-201",
        task_id="task-101",
        file_path="/workspace/deploy.log",
        file_type="text/plain",
        file_size_bytes=1024,
        created_at_ms=now_ms,
    )

    aggregator = TrajectoryAggregator()
    items = aggregator.aggregate_from_delegation(
        tasks=[task_1, task_out_of_range],
        artifacts=[art_1],
        start_time_ms=start_ms,
        end_time_ms=end_ms,
    )

    assert len(items) == 1
    assert items[0].source_id == "task-101"
    assert "/workspace/deploy.log" in items[0].artifact_paths
    assert "Deploy production microservice" in items[0].title


def test_weekly_report_generation_engineer_mode() -> None:
    """Verifies weekly report rendering in engineer mode."""
    now_ms = int(time.time() * 1000)
    start_ms, end_ms = TrajectoryAggregator.get_natural_week_window(now_ms)

    task = DelegationTask(
        task_id="task-201",
        session_id="session-2",
        channel_id="wechat",
        instruction="Refactor auth gateway",
        created_at_ms=now_ms,
        updated_at_ms=now_ms,
        status=DelegationStatus.SUCCEEDED,
        execution_summary="Refactored JWT signature verification",
        artifact_paths=("/workspace/auth.py",),
    )

    aggregator = TrajectoryAggregator()
    trajectories = aggregator.aggregate_from_delegation([task], [], start_ms, end_ms)

    sop_service = WeeklyReportSOPService()
    report = sop_service.generate_report(trajectories, start_ms, end_ms, ReportRoleMode.ENGINEER)

    assert report.role_mode == ReportRoleMode.ENGINEER
    assert "工作周报" in report.title
    assert "一、核心技术交付与工件输出" in report.markdown_content
    assert "Refactor auth gateway" in report.markdown_content
    assert "/workspace/auth.py" in report.attached_artifacts


def test_weekly_report_empty_fallback() -> None:
    """Verifies fallback message when no tasks exist."""
    now_ms = int(time.time() * 1000)
    start_ms, end_ms = TrajectoryAggregator.get_natural_week_window(now_ms)

    sop_service = WeeklyReportSOPService()
    report = sop_service.generate_report([], start_ms, end_ms, ReportRoleMode.GENERAL)

    assert "本周暂无记录的沙箱委派任务" in report.markdown_content
    assert len(report.attached_artifacts) == 0


def test_wiki_ingestion_and_dedup() -> None:
    """Verifies chat decision ingestion and deduplication guard."""
    service = WikiIngestionService()
    title = "Database Migration Strategy"
    content = "Decided to adopt Alembic for declarative schema migrations."
    fp = WikiIngestionService.compute_fingerprint(title, content)

    payload = WikiIngestPayload(
        channel_id="feishu",
        topic_title=title,
        content_raw=content,
        tags=("architecture", "database"),
        fingerprint_sha256=fp,
        created_at_ms=int(time.time() * 1000),
    )

    res1 = service.ingest_chat_decision(payload)
    assert res1.success is True
    assert res1.is_duplicate is False
    assert res1.wiki_path == "decisions/database_migration_strategy.md"

    # Second ingestion with same fingerprint should detect duplicate
    res2 = service.ingest_chat_decision(payload)
    assert res2.success is True
    assert res2.is_duplicate is True
