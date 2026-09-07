"""Unit tests for organizational trajectory aggregator, weekly report SOP generator, and wiki archiving.

Covers:
- Multi-source trajectory aggregation across production, business, and management chains.
- Period boundary filtering and event sorting.
- Markdown rendering with real artifact evidence.
- Interactive card generation for IM distribution.
- Chat-to-Knowledge wiki drafting.
"""

from __future__ import annotations

import time

from app.services.trajectory.trajectory_aggregator import TrajectoryAggregator
from app.services.trajectory.trajectory_models import (
    TrajectoryArtifactRef,
    ValueChainType,
)
from app.services.trajectory.weekly_report_service import WeeklyReportSOPService


def test_trajectory_aggregator_multi_chain_recording() -> None:
    aggregator = TrajectoryAggregator()
    now = time.time()

    # 1. Record production task with artifacts
    art = TrajectoryArtifactRef(
        artifact_id="art_001",
        filename="bundle.tar.gz",
        artifact_type="archive",
        relative_path="dist/bundle.tar.gz",
        byte_size=1048576,
    )
    prod_evt = aggregator.record_production_task(
        task_id="task_1001",
        title="完成支付网关反向代理部署",
        summary="自动配置 Nginx 443 端口与 SSL 证书，测试通过",
        artifacts=[art],
        is_completed=True,
        timestamp=now - 3600 * 24 * 2,  # 2 days ago
    )
    assert prod_evt.chain_type == ValueChainType.PRODUCTION
    assert len(prod_evt.artifacts) == 1

    # 2. Record business requirement milestone
    biz_evt = aggregator.record_business_decision(
        title="确认 Q3 渠道集成技术架构选型",
        summary="选定以 IM 委派调度与日志蒸馏为核心落地路径",
        source_channel="feishu_group",
        timestamp=now - 3600 * 24 * 3,  # 3 days ago
    )
    assert biz_evt.chain_type == ValueChainType.BUSINESS

    # 3. Record management approval
    mgmt_evt = aggregator.record_management_approval(
        approval_id="appr_501",
        action_name="生产环境高危配置变更",
        approver="Tech Lead",
        decision="同意执行",
        timestamp=now - 3600 * 24 * 1,  # 1 day ago
    )
    assert mgmt_evt.chain_type == ValueChainType.MANAGEMENT

    # Aggregate for last 7 days
    events = aggregator.aggregate_for_period(start_time=now - 3600 * 24 * 7, end_time=now)
    assert len(events) == 3
    # Check chronological ordering
    assert events[0].timestamp <= events[1].timestamp <= events[2].timestamp


def test_weekly_report_sop_generation_and_markdown_rendering() -> None:
    aggregator = TrajectoryAggregator()
    now = time.time()
    service = WeeklyReportSOPService(aggregator=aggregator)

    # Populate test events
    art = TrajectoryArtifactRef(
        artifact_id="art_002",
        filename="nginx_patch.conf",
        artifact_type="config",
        relative_path="conf/nginx_patch.conf",
        byte_size=2048,
    )
    aggregator.record_production_task(
        task_id="task_2001",
        title="完成 IM 远程运维自然语言派单组件",
        summary="实现 0.3s 毫秒级即时回执与 96% Token 压缩日志蒸馏引擎",
        artifacts=[art],
        is_completed=True,
        timestamp=now - 3600 * 20,
    )
    aggregator.record_business_decision(
        title="统一多渠道卡片交互规范",
        summary="飞书、企微、微信统一复用标准 JSON 渲染卡片协议",
        timestamp=now - 3600 * 10,
    )

    # Generate report
    payload = service.generate_weekly_report(
        start_time=now - 3600 * 24 * 7,
        end_time=now,
        author_name="Alice Developer",
    )

    assert payload.author_name == "Alice Developer"
    assert len(payload.completed_highlights) == 2
    assert len(payload.referenced_artifacts) == 1

    md_text = payload.to_markdown()
    assert "# 📊 个人/团队工作周报" in md_text
    assert "Alice Developer" in md_text
    assert "完成 IM 远程运维自然语言派单组件" in md_text
    assert "nginx_patch.conf" in md_text


def test_weekly_report_interactive_card_rendering() -> None:
    service = WeeklyReportSOPService()
    now = time.time()
    payload = service.generate_weekly_report(
        start_time=now - 3600 * 24 * 7,
        end_time=now,
        author_name="Bob Engineer",
    )

    card = service.build_report_interactive_card(payload)
    assert card["card_type"] == "weekly_report_summary"
    assert card["title"] == "📊 工作周报 · Bob Engineer"
    assert "actions" in card
    actions = card["actions"]
    assert isinstance(actions, list)
    assert len(actions) == 3


def test_chat_to_knowledge_wiki_archiving() -> None:
    service = WeeklyReportSOPService()
    draft = service.archive_chat_to_wiki(
        topic_title="支付系统幂等性设计与防重试规范",
        discussion_content="1. 所有下单与扣费接口必须携带 X-Request-ID。\n2. Redis 分布式锁兜底，锁超时 30 秒。\n3. 数据库唯一索引阻断重复插入。",
        category="架构决策",
        tags=["支付", "幂等性", "规范"],
    )

    assert draft.title == "支付系统幂等性设计与防重试规范"
    assert draft.category == "架构决策"
    assert "X-Request-ID" in draft.markdown_content
    assert draft.tags == ("支付", "幂等性", "规范")
