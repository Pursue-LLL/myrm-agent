"""Unit and integration tests for cross-platform task delegation, steering, and delivery hub."""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.delegation import (
    DelegationCoordinator,
    DelegationIngressGuard,
    DelegationStatus,
    RiskLevel,
    build_delivery_card_content,
    build_delegation_task,
    format_file_size,
    is_delegation_intent,
    scan_workspace_artifacts,
)
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage, StreamingText

# ── Ingress Intent Tests ──────────────────────────────────────────────


def test_is_delegation_intent_explicit_and_heuristics() -> None:
    """Test explicit prefixes and long-running keyword intent detection."""
    # Explicit prefixes
    is_del, conf, prompt = is_delegation_intent("/delegate 分析 10 家跨端竞品并做成PPT")
    assert is_del is True
    assert conf == 1.0
    assert "分析 10 家跨端竞品并做成PPT" in prompt

    is_del, conf, prompt = is_delegation_intent("/async 爬取全网财报")
    assert is_del is True
    assert conf == 1.0
    assert prompt == "爬取全网财报"

    is_del, conf, prompt = is_delegation_intent("【后台任务】通宵运行自动化测试")
    assert is_del is True
    assert conf == 1.0

    # Heuristic keywords
    is_del, conf, prompt = is_delegation_intent("把昨天那个方案做成ppt并明早给我")
    assert is_del is True
    assert conf >= 0.85

    # Fast query should NOT match
    is_del, conf, _ = is_delegation_intent("今天北京天气怎么样？")
    assert is_del is False
    assert conf == 0.0


def test_delegation_ingress_guard_concurrency() -> None:
    """Test max 2 concurrent delegations per user/channel."""
    guard = DelegationIngressGuard(max_active_per_user=2)
    channel = "feishu"
    user_id = "user_123"

    assert guard.can_accept(channel, user_id) is True
    guard.acquire(channel, user_id, "task_1")
    assert guard.can_accept(channel, user_id) is True
    guard.acquire(channel, user_id, "task_2")
    assert guard.can_accept(channel, user_id) is False

    guard.release(channel, user_id, "task_1")
    assert guard.can_accept(channel, user_id) is True


# ── Coordinator Lifecycle Tests ───────────────────────────────────────


@pytest.mark.asyncio
async def test_coordinator_lifecycle_and_steering() -> None:
    """Test registration, status transition, steering, and approval relay."""
    coordinator = DelegationCoordinator()
    task = build_delegation_task(
        origin_channel="telegram",
        origin_user_id="user_456",
        origin_chat_id="chat_789",
        raw_prompt="生成竞品报告",
        normalized_prompt="生成竞品报告",
    )

    coordinator.register_task(task)
    assert coordinator.get_task(task.task_id) is not None

    active = coordinator.find_active_task("telegram", "user_456")
    assert active is not None
    assert active.task_id == task.task_id

    # Transition to running
    coordinator.update_task_status(task.task_id, DelegationStatus.RUNNING)
    assert task.status == DelegationStatus.RUNNING

    # Steering injection
    steered = coordinator.inject_steering(task.task_id, "重点分析内存开销", "user_456")
    assert steered is True

    # Remote approval flow
    approval_task = asyncio.create_task(
        coordinator.request_remote_approval(
            task.task_id,
            action_name="execute_terminal",
            action_summary="执行 rm -rf /tmp/build",
            risk_level=RiskLevel.HIGH,
            timeout_seconds=5.0,
        )
    )

    await asyncio.sleep(0.01)
    pending_req = coordinator.get_pending_approval_by_task(task.task_id)
    assert pending_req is not None

    resolved = coordinator.resolve_approval(pending_req.request_id, "approve", "user_456")
    assert resolved is True

    resp = await approval_task
    assert resp.decision == "approve"
    assert resp.responder_id == "user_456"


def test_coordinator_reap_stale_tasks() -> None:
    """Test watchdog reaping of timed out tasks."""
    coordinator = DelegationCoordinator()
    task = build_delegation_task(
        origin_channel="wechat",
        origin_user_id="user_timeout",
        origin_chat_id="chat_timeout",
        raw_prompt="测试超时任务",
        normalized_prompt="测试超时任务",
        timeout_seconds=0.1,
    )
    coordinator.register_task(task)
    task.started_at = 1.0  # long ago in the past

    reaped = coordinator.reap_stale_tasks(max_age_seconds=1.0)
    assert task.task_id in reaped
    assert task.status == DelegationStatus.FAILED


# ── Delivery Artifact Scanning Tests ─────────────────────────────────


def test_scan_workspace_artifacts_and_card(tmp_path: Path) -> None:
    """Test finding deliverables and rendering rich card."""
    workspace = tmp_path / "sandbox"
    workspace.mkdir()

    # Create dummy deliverable files
    ppt_file = workspace / "Competitor_Analysis.pptx"
    ppt_file.write_bytes(b"PK\x03\x04dummy_pptx_data")

    xlsx_file = workspace / "Q3_Budget.xlsx"
    xlsx_file.write_bytes(b"PK\x03\x04dummy_xlsx_data")

    artifacts = scan_workspace_artifacts(workspace, server_base_url="https://agent.myrm.io")
    assert len(artifacts) == 2

    task = build_delegation_task(
        origin_channel="feishu",
        origin_user_id="user_feishu",
        origin_chat_id="chat_feishu",
        raw_prompt="生成竞品 PPT 和预算表",
        normalized_prompt="生成竞品 PPT 和预算表",
    )
    task.status = DelegationStatus.COMPLETED
    task.artifacts = artifacts
    card = build_delivery_card_content(task, artifacts, server_base_url="https://agent.myrm.io")

    assert "Competitor_Analysis.pptx" in card
    assert "Q3_Budget.xlsx" in card
    assert "https://agent.myrm.io" in card
    assert "✅" in card




def test_format_file_size() -> None:
    """Test byte humanization helper."""
    assert format_file_size(500) == "500 B"
    assert format_file_size(2048) == "2.0 KB"
    assert format_file_size(5 * 1024 * 1024) == "5.0 MB"


# ── AgentRouter Integration Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_router_delegation_inbound_integration(tmp_path: Path) -> None:
    """Test full inbound routing flow: receipt echo, background execution, and deliverable delivery."""
    bus = MagicMock()
    bus.consume_inbound = AsyncMock(side_effect=TimeoutError)
    bus.publish_outbound = AsyncMock()
    bus.get_channel = MagicMock(return_value=None)

    pairing = MagicMock()

    # Mock agent executor that yields streaming text events
    async def _mock_stream(msg: InboundMessage, user_id: str, **kwargs: object):
        yield StreamingText(text="已完成市场研报全量分析，并在沙箱中生成汇报 PPT。")

    executor = MagicMock()
    executor.execute_stream = _mock_stream

    router = AgentRouter(
        bus=bus,
        pairing_store=pairing,
        agent_executor=executor,
    )

    inbound = InboundMessage(
        channel="feishu",
        sender_id="ou_mobile_user_1",
        chat_id="oc_group_chat_1",
        content="/delegate 分析 2026 年行业动向并生成汇报 PPT",
        user_id="ou_mobile_user_1",
    )

    # Dispatch via _handle_delegation_inbound directly
    handled = await router._handle_delegation_inbound(inbound, "分析 2026 年行业动向并生成汇报 PPT")
    assert handled is True

    # 1. Verify immediate receipt outbound message (<1s)
    assert bus.publish_outbound.call_count >= 1
    receipt_call = bus.publish_outbound.call_args_list[0]
    receipt_outbound = receipt_call[0][0]
    assert receipt_outbound.recipient_id == "oc_group_chat_1"
    assert "已收到异步任务委派" in receipt_outbound.content
    assert receipt_outbound.metadata.get("is_receipt") is True

    # Allow background execution task to run
    await asyncio.sleep(0.1)

    # 2. Verify second outbound message for delivery
    assert bus.publish_outbound.call_count >= 2
    delivery_call = bus.publish_outbound.call_args_list[1]
    delivery_outbound = delivery_call[0][0]
    assert "任务交付通知" in delivery_outbound.content
