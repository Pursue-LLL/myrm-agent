"""Unit tests for Three Value Chains Trajectory Aggregator and Weekly Report SOP Service."""

import time
import pytest

from app.channels.delegation.delegation_models import (
    DelegationStatus,
    DelegationTask,
    DeliveryArtifact,
)
from app.channels.delegation.trajectory_aggregator import (
    TrajectoryAggregator,
    ValueChainType,
)
from app.channels.delegation.weekly_report_sop import (
    WeeklyReportSOPService,
)


def test_trajectory_aggregator_empty() -> None:
    """Test aggregation with no tasks or decisions."""
    now = time.time()
    trajectory = TrajectoryAggregator.aggregate(
        user_id="user_test_123",
        tasks=[],
        channel_decisions=[],
        time_window_start=now - 3600,
        time_window_end=now,
    )

    assert trajectory.user_id == "user_test_123"
    assert trajectory.total_tasks_executed == 0
    assert trajectory.total_artifacts_produced == 0
    assert len(trajectory.production_items) == 0
    assert len(trajectory.business_items) == 0
    assert len(trajectory.management_items) == 0


def test_trajectory_aggregator_with_tasks_and_artifacts() -> None:
    """Test multi-chain trajectory extraction from completed/failed tasks and artifacts."""
    now = time.time()
    task_success = DelegationTask(
        task_id="tsk_succ_001",
        origin_channel="feishu",
        origin_user_id="user_test_123",
        origin_chat_id="chat_001",
        raw_prompt="重构数据模型并导出 SQL",
        normalized_prompt="重构数据模型并导出 SQL",
        status=DelegationStatus.COMPLETED,
        created_at=now - 1000,
        completed_at=now - 500,
        result_summary="成功重构完成并通过全量单测",
        artifacts=[
            DeliveryArtifact(
                file_name="schema_v2.sql",
                file_path="/sandbox/output/schema_v2.sql",
                file_size_bytes=2048,
                sha256_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                created_at=now - 500,
            )
        ],
    )

    task_failed = DelegationTask(
        task_id="tsk_fail_002",
        origin_channel="discord",
        origin_user_id="user_test_123",
        origin_chat_id="chat_002",
        raw_prompt="部署测试集群",
        normalized_prompt="部署测试集群",
        status=DelegationStatus.FAILED,
        created_at=now - 2000,
        completed_at=now - 1800,
        error_message="网络连接超时，上游镜像源不可达",
    )

    decisions = [
        {
            "topic": "统一接入 OAuth2.0 鉴权",
            "detail": "架构团队一致通过使用 PKCE 模式替代隐式授权",
            "channel": "feishu_arch_group",
            "timestamp": str(now - 1200),
        }
    ]

    trajectory = TrajectoryAggregator.aggregate(
        user_id="user_test_123",
        tasks=[task_success, task_failed],
        channel_decisions=decisions,
        time_window_start=now - 86400,
        time_window_end=now,
    )

    assert trajectory.total_tasks_executed == 2
    assert trajectory.total_artifacts_produced == 1
    assert len(trajectory.production_items) == 2  # 1 task + 1 artifact
    assert len(trajectory.management_items) == 1  # 1 risk (failed task)
    assert len(trajectory.business_items) == 1  # 1 channel decision

    # Verify chain types
    assert trajectory.production_items[0].chain_type == ValueChainType.PRODUCTION
    assert trajectory.management_items[0].chain_type == ValueChainType.MANAGEMENT
    assert trajectory.business_items[0].chain_type == ValueChainType.BUSINESS


def test_weekly_report_sop_service_generation() -> None:
    """Test full SOP markdown report generation and Feishu card rendering."""
    now = time.time()
    task_success = DelegationTask(
        task_id="tsk_001",
        origin_channel="feishu",
        origin_user_id="user_alpha",
        origin_chat_id="chat_alpha",
        raw_prompt="优化搜索引擎向量召回",
        normalized_prompt="优化搜索引擎向量召回",
        status=DelegationStatus.COMPLETED,
        created_at=now - 3600,
        completed_at=now - 1800,
        result_summary="召回率提升 15%，延迟下降至 12ms",
        artifacts=[
            DeliveryArtifact(
                file_name="benchmark_report.pdf",
                file_path="/output/benchmark_report.pdf",
                file_size_bytes=1048576,
                sha256_hash="abc12345def67890",
                created_at=now - 1800,
            )
        ],
    )

    trajectory = TrajectoryAggregator.aggregate(
        user_id="user_alpha",
        tasks=[task_success],
        channel_decisions=[
            {
                "topic": "确定 Q4 研发基准版本",
                "detail": "锁定 Python 3.13 与 Next.js 15 为主线版本",
                "channel": "dingtalk",
                "timestamp": str(now - 2000),
            }
        ],
        time_window_start=now - 86400 * 7,
        time_window_end=now,
    )

    report = WeeklyReportSOPService.generate_report(trajectory)

    assert report.total_tasks_completed == 1
    assert report.total_artifacts_produced == 1
    assert report.total_risks_identified == 0
    assert "一、 🚀 本周核心产出与交付（生产链）" in report.markdown_content
    assert "优化搜索引擎向量召回" in report.markdown_content
    assert "benchmark_report.pdf" in report.markdown_content
    assert "确定 Q4 研发基准版本" in report.markdown_content

    # Test Feishu Card rendering
    card = WeeklyReportSOPService.render_feishu_card(report)
    assert card["header"]["template"] == "blue"
    assert len(card["elements"]) >= 3
    assert "周报周期" in card["elements"][0]["text"]["content"]
