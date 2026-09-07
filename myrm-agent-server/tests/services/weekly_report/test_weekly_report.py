"""Unit tests for Weekly Report SOP, Trajectory Aggregator, and Chat-to-Knowledge Extractor."""

from __future__ import annotations

import time

from app.services.weekly_report import (
    ChatKnowledgeExtractRequest,
    ChatToKnowledgeArchiver,
    TrajectoryAggregator,
    TrajectoryEventSource,
    WeeklyReportService,
)


def test_trajectory_aggregator_recording_and_filtering() -> None:
    """Test recording heterogeneous events and filtering by source, time, and tags."""
    aggregator = TrajectoryAggregator()
    now = time.time()

    # Record sandbox task
    sandbox_event = aggregator.record_sandbox_task(
        task_id="task_101",
        title="Deploy Redis Sentinel",
        summary="Completed auto-failover configuration in sandbox",
        channel="feishu_ops",
        tags=["sandbox", "database"],
    )
    assert sandbox_event.source == TrajectoryEventSource.SANDBOX_EXECUTION
    assert sandbox_event.task_id == "task_101"

    # Record artifact
    artifact_event = aggregator.record_artifact(
        task_id="task_101",
        artifact_path="/workspace/config/redis.conf",
        artifact_hash="a1b2c3d4e5f67890",
        title="Redis Sentinel Configuration File",
        summary="High-availability cluster settings",
        channel="feishu_ops",
    )
    assert artifact_event.source == TrajectoryEventSource.DELIVERY_ARTIFACT
    assert artifact_event.artifact_hash == "a1b2c3d4e5f67890"

    # Record chat decision
    chat_event = aggregator.record_chat_decision(
        session_id="session_888",
        title="Architecture Decision: Adopt Redis 7.2",
        decision_summary="Team agreed to standardize on Redis 7.2 engine across clusters",
        channel="feishu_ops",
    )
    assert chat_event.source == TrajectoryEventSource.CHAT_DECISION

    # Filter by source
    sandbox_events = aggregator.get_events(source=TrajectoryEventSource.SANDBOX_EXECUTION)
    assert len(sandbox_events) == 1
    assert sandbox_events[0].title == "Deploy Redis Sentinel"

    # Filter by tag
    db_events = aggregator.get_events(tag="database")
    assert len(db_events) == 1

    # Filter by time window
    all_events = aggregator.get_events(start_time=now - 10, end_time=now + 10)
    assert len(all_events) == 3


def test_chat_to_knowledge_extraction() -> None:
    """Test extracting structured decisions and Markdown Wiki pages from chat conversations."""
    raw_chat = (
        "# RFC-042: Model Routing Strategy\n"
        "After benchmarking Gemini 3.8 and MiniMax, we decided to use Gemini as Basic LLM\n"
        "and MiniMax M3 as Fast/Lite LLM for sub-second summarization.\n"
        "Action item: update .env.test and server provider configurations."
    )

    req = ChatKnowledgeExtractRequest(
        chat_context=raw_chat,
        channel="wechat_work_ai_team",
        session_id="sess_12345",
        target_wiki_category="engineering/routing",
        author="alice",
    )

    result = ChatToKnowledgeArchiver.extract_from_chat(req)

    assert result.success is True
    assert "RFC-042: Model Routing Strategy" in result.concept_title
    assert result.wiki_rel_path.startswith("engineering/routing/")
    assert "---" in result.markdown_content
    assert "source_channel: wechat_work_ai_team" in result.markdown_content
    assert "## Context & Consensus" in result.markdown_content


def test_chat_to_knowledge_empty_context() -> None:
    """Test edge case with empty chat context."""
    req = ChatKnowledgeExtractRequest(
        chat_context="   ",
        channel="telegram",
        session_id="sess_empty",
    )
    result = ChatToKnowledgeArchiver.extract_from_chat(req)
    assert result.success is False
    assert result.error_message == "Empty chat context provided"


def test_weekly_report_generation_full_pipeline() -> None:
    """Test end-to-end weekly report assembly with evidence chains."""
    aggregator = TrajectoryAggregator()

    # Populate multiple events
    aggregator.record_sandbox_task(
        task_id="task_201",
        title="Migrated Database Schema",
        summary="Applied migration v3.2 for trajectory audit tables",
    )
    aggregator.record_artifact(
        task_id="task_201",
        artifact_path="migrations/v3_2.sql",
        artifact_hash="7f8e9d0c1b2a",
        title="V3.2 Migration Script",
        summary="SQL script with idempotent table definitions",
    )
    aggregator.record_chat_decision(
        session_id="session_999",
        title="Weekly Release Consensus",
        decision_summary="Agreed to ship 2.4.0 on Thursday afternoon",
        channel="lark_team",
    )

    service = WeeklyReportService(aggregator=aggregator)
    report = service.generate_report(
        title="Engineering Sprint Report",
        author="Myrm AI Lead",
        period_days=7,
    )

    assert report.total_events_aggregated == 3
    assert len(report.sections) == 4
    assert "Engineering Sprint Report" in report.raw_markdown
    assert "Migrated Database Schema" in report.raw_markdown
    assert "V3.2 Migration Script" in report.raw_markdown
    assert "Weekly Release Consensus" in report.raw_markdown
    assert "7f8e9d0c1b2a" in report.raw_markdown


def test_weekly_report_empty_period_graceful() -> None:
    """Test generating a report when no events exist in the period."""
    aggregator = TrajectoryAggregator()
    service = WeeklyReportService(aggregator=aggregator)

    report = service.generate_report(title="Empty Week Report")
    assert report.total_events_aggregated == 0
    assert "No sandbox tasks recorded" in report.raw_markdown
    assert "No new artifacts generated" in report.raw_markdown
