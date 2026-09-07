"""Unit tests for weekly report SOP, trajectory aggregator, and chat-to-knowledge service.

Verifies event recording, time-window filtering, report markdown formatting, and wiki extraction.
"""

from __future__ import annotations

import time

from app.services.weekly_report.chat_to_knowledge import ChatToKnowledgeArchiver
from app.services.weekly_report.models import (
    ChatKnowledgeExtractRequest,
    TrajectoryEventSource,
)
from app.services.weekly_report.trajectory_aggregator import TrajectoryAggregator
from app.services.weekly_report.weekly_report_service import WeeklyReportService


def test_trajectory_aggregator_recording_and_filtering() -> None:
    """Verifies events are correctly recorded, filtered by source, tag, and time window."""
    aggregator = TrajectoryAggregator()
    now = time.time()

    # 1. Record sandbox task
    e1 = aggregator.record_sandbox_task(
        task_id="task-101",
        title="Deploy Auth Service",
        summary="Deployed auth container on port 8080",
        channel="feishu",
        tags=["deployment", "auth"],
    )
    assert e1.source == TrajectoryEventSource.SANDBOX_EXECUTION
    assert e1.task_id == "task-101"

    # 2. Record artifact
    e2 = aggregator.record_artifact(
        task_id="task-101",
        artifact_path="/workspace/build.log",
        artifact_hash="abcdef1234567890",
        title="Build Log Artifact",
        summary="Successful clean build output",
        channel="feishu",
    )
    assert e2.source == TrajectoryEventSource.DELIVERY_ARTIFACT
    assert e2.artifact_path == "/workspace/build.log"

    # 3. Record chat decision
    e3 = aggregator.record_chat_decision(
        session_id="session-999",
        title="Adopt Qdrant for Memory Store",
        decision_summary="Agreed to use Qdrant for high-throughput semantic memory.",
        channel="wechat",
    )
    assert e3.source == TrajectoryEventSource.CHAT_DECISION

    # Filter by source
    sandbox_events = aggregator.get_events(source=TrajectoryEventSource.SANDBOX_EXECUTION)
    assert len(sandbox_events) == 1
    assert sandbox_events[0].event_id == e1.event_id

    # Filter by tag
    auth_events = aggregator.get_events(tag="auth")
    assert len(auth_events) == 1

    # Filter by time window
    window_events = aggregator.get_events(start_time=now - 10, end_time=now + 10)
    assert len(window_events) == 3


def test_weekly_report_service_generation() -> None:
    """Verifies weekly report document structure and markdown rendering."""
    aggregator = TrajectoryAggregator()
    aggregator.record_sandbox_task(
        task_id="task-202",
        title="Database Optimization",
        summary="Added composite indexes on user_id and created_at",
        channel="telegram",
    )
    aggregator.record_artifact(
        task_id="task-202",
        artifact_path="/workspace/migration.sql",
        artifact_hash="1122334455667788",
        title="SQL Migration Script",
        summary="Schema migration script for index updates",
    )
    aggregator.record_chat_decision(
        session_id="session-303",
        title="Standardize on Pytest Safe Runner",
        decision_summary="Enforced run-pytest-safe.sh wrapper for test harness.",
        channel="feishu",
    )

    service = WeeklyReportService(aggregator=aggregator)
    report = service.generate_report(
        title="Engineering Sprint Weekly",
        author="Lead AI Engineer",
        period_days=7,
    )

    assert report.title == "Engineering Sprint Weekly"
    assert report.author == "Lead AI Engineer"
    assert report.total_events_aggregated == 3
    assert len(report.sections) == 4

    # Verify Markdown contains evidence
    md = report.raw_markdown
    assert "# Engineering Sprint Weekly" in md
    assert "Database Optimization" in md
    assert "SQL Migration Script" in md
    assert "Standardize on Pytest Safe Runner" in md
    assert "Generated automatically by Myrm" in md


def test_chat_to_knowledge_extractor() -> None:
    """Verifies chat decision distillation to Markdown wiki with frontmatter."""
    chat_text = (
        "# RFC: Redis Caching Layer\n\n"
        "After team discussion, we concluded that Redis should be deployed with cluster mode enabled.\n"
        "TTL strategy is set to 3600 seconds for session tokens."
    )
    req = ChatKnowledgeExtractRequest(
        chat_context=chat_text,
        channel="feishu",
        session_id="sess-777",
        target_wiki_category="architecture/rfc",
        author="architect",
    )

    res = ChatToKnowledgeArchiver.extract_from_chat(req)
    assert res.success is True
    assert res.concept_title == "RFC: Redis Caching Layer"
    assert res.wiki_rel_path == "architecture/rfc/rfc_redis_caching_layer.md"
    assert "title: RFC: Redis Caching Layer" in res.markdown_content
    assert "source_channel: feishu" in res.markdown_content
    assert "## Context & Consensus" in res.markdown_content


def test_chat_to_knowledge_empty_context() -> None:
    """Verifies graceful handling of empty chat input."""
    req = ChatKnowledgeExtractRequest(
        chat_context="   ",
        channel="wechat",
        session_id="sess-0",
    )
    res = ChatToKnowledgeArchiver.extract_from_chat(req)
    assert res.success is False
    assert res.error_message == "Empty chat context provided"
