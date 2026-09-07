"""Unit and regression tests for TrajectoryAggregator and WeeklyReportSOPService.

Validates:
1. Multi-source task classification and metric aggregation.
2. Executive-ready Markdown weekly report rendering and completion rate calculations.
3. Chat-to-Knowledge Wiki decision archiving and directory structure creation.
"""

import time
from pathlib import Path

from app.channels.delegation.delegation_models import (
    DelegationStatus,
    DelegationTask,
    DeliveryArtifact,
)
from app.channels.delegation.trajectory_aggregator import (
    GroupDecisionItem,
    TrajectoryAggregator,
    TrajectoryCategory,
)
from app.channels.delegation.weekly_report_sop import (
    WeeklyReportSOPService,
)


def test_trajectory_task_classification() -> None:
    aggregator = TrajectoryAggregator()

    t_bug = DelegationTask(
        task_id="t1",
        origin_channel="feishu",
        origin_user_id="u1",
        raw_prompt="修复生产环境支付回调 500 报错",
        status=DelegationStatus.COMPLETED,
    )
    assert aggregator.classify_task_category(t_bug) == TrajectoryCategory.BUGFIX

    t_deploy = DelegationTask(
        task_id="t2",
        origin_channel="wechat",
        origin_user_id="u1",
        raw_prompt="一键部署 Docker 容器到预发集群",
        status=DelegationStatus.COMPLETED,
    )
    assert aggregator.classify_task_category(t_deploy) == TrajectoryCategory.DEPLOYMENT

    t_dev = DelegationTask(
        task_id="t3",
        origin_channel="webui",
        origin_user_id="u1",
        raw_prompt="实现基于 Trajectory 的周报自动生成模块",
        status=DelegationStatus.COMPLETED,
    )
    assert aggregator.classify_task_category(t_dev) == TrajectoryCategory.DEVELOPMENT


def test_trajectory_aggregation_metrics() -> None:
    aggregator = TrajectoryAggregator()
    now = time.time()

    art1 = DeliveryArtifact(file_name="report.pdf", file_path="/tmp/report.pdf", file_size_bytes=20480)
    art2 = DeliveryArtifact(file_name="patch.diff", file_path="/tmp/patch.diff", file_size_bytes=4096)

    t1 = DelegationTask(
        task_id="task_1",
        origin_channel="feishu",
        origin_user_id="alice",
        raw_prompt="优化数据库索引",
        status=DelegationStatus.COMPLETED,
        started_at=now - 100,
        completed_at=now - 10,
        result_summary="QPS 提升 40%",
        artifacts=[art1],
    )

    t2 = DelegationTask(
        task_id="task_2",
        origin_channel="feishu",
        origin_user_id="alice",
        raw_prompt="重构前端组件库",
        status=DelegationStatus.RUNNING,
        started_at=now - 50,
    )

    t3 = DelegationTask(
        task_id="task_3",
        origin_channel="feishu",
        origin_user_id="bob",  # Other user
        raw_prompt="配置 CI 流水线",
        status=DelegationStatus.COMPLETED,
        artifacts=[art2],
    )

    decision = GroupDecisionItem(
        decision_id="dec_1",
        topic="API 鉴权方案选型",
        summary="采用 JWT + Redis 白名单机制",
        decision_maker="alice",
        channel_id="tech_chat_01",
        timestamp=now - 20,
        tags=["security", "auth"],
    )

    traj = aggregator.aggregate_from_tasks(
        [t1, t2, t3],
        user_id="alice",
        start_time=now - 200,
        end_time=now,
        decisions=[decision],
    )

    assert len(traj.completed_items) == 1
    assert len(traj.in_progress_items) == 1
    assert len(traj.failed_items) == 0
    assert len(traj.artifacts) == 1
    assert len(traj.decisions) == 1
    assert traj.total_tasks_count == 2
    assert traj.completion_rate == 0.5


def test_weekly_report_sop_rendering(tmp_path: Path) -> None:
    sop = WeeklyReportSOPService(wiki_root_dir=tmp_path)
    now = time.time()

    art = DeliveryArtifact(file_name="deploy.sh", file_path="/tmp/deploy.sh", file_size_bytes=1024)
    t = DelegationTask(
        task_id="t1",
        origin_channel="feishu",
        origin_user_id="u1",
        raw_prompt="构建跨渠道周报服务",
        status=DelegationStatus.COMPLETED,
        started_at=now - 30,
        completed_at=now,
        result_summary="已完成全链路测试并通过验收",
        artifacts=[art],
    )

    aggregator = TrajectoryAggregator()
    traj = aggregator.aggregate_from_tasks([t], user_id="u1", start_time=now - 100, end_time=now)

    payload = sop.render_weekly_report(traj, user_display_name="张工")

    assert payload.total_tasks_completed == 1
    assert payload.total_artifacts_produced == 1
    assert payload.completion_rate_percent == 100
    assert "张工" in payload.markdown_content
    assert "构建跨渠道周报服务" in payload.markdown_content
    assert "deploy.sh" in payload.markdown_content


def test_chat_decision_archive_to_wiki(tmp_path: Path) -> None:
    sop = WeeklyReportSOPService(wiki_root_dir=tmp_path)

    decision = GroupDecisionItem(
        decision_id="d100",
        topic="支付网关容灾规范",
        summary="主备通道 100ms 自动探测并切换",
        decision_maker="李工",
        channel_id="feishu_group_99",
        timestamp=time.time(),
        related_task_ids=["t1", "t2"],
        tags=["payment", "ha"],
    )

    res = sop.archive_chat_decision_to_wiki(decision, subfolder="tech_specs")
    assert res.success is True
    assert Path(res.file_path).exists()

    file_content = Path(res.file_path).read_text(encoding="utf-8")
    assert "支付网关容灾规范" in file_content
    assert "主备通道 100ms 自动探测并切换" in file_content
    assert "李工" in file_content
