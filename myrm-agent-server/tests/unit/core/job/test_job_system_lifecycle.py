"""不可摧毁作业系统全生命周期与自愈契约自动化测试套件。

覆盖切片 CAS Claim、防脑裂 Fencing Token、租约心跳熔断、
四级现场求证对账自愈、切片边界输入摄入、文件原子追加校验与 Cron 适配。
"""

from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.runtime.segment_guard import (
    AtomicSegmentAppender,
    BoundedSegmentBudget,
    StepBudgetExceededError,
    TailMismatchError,
)
from myrm_agent_harness.toolkits.cron.engine.cron_job_adapter import (
    CronExecutionDecision,
    CronJobAdapter,
)

from app.core.job.lease_heartbeat import LeaseContext, LeaseLostError
from app.core.job.models import (
    CheckpointEvidence,
    InputStatus,
    ReconciliationAction,
    RunStatus,
    SegmentStatus,
)
from app.core.job.reconciliation import CheckpointReconciler
from app.core.job.store import JobStore
from app.core.job.supervisor import JobSupervisor


@pytest.mark.asyncio
async def test_normal_segment_lifecycle_and_run_completion() -> None:
    """测试常规切片认领、租约续约与顺利结算，驱动 Run 状态流转。"""
    store = JobStore()
    supervisor = JobSupervisor(store)

    run = await store.create_run(run_id="run_1", conversation_id="conv_1")
    assert run.status == RunStatus.PENDING

    await store.create_segment(segment_id="seg_1", run_id="run_1", sequence_index=0)

    # Worker A 认领切片
    claimed = await store.claim_next_segment(worker_id="worker_a", lease_seconds=60.0)
    assert claimed is not None
    assert claimed.segment_id == "seg_1"
    assert claimed.owner_id == "worker_a"
    assert claimed.fencing_token == 1
    assert claimed.status == SegmentStatus.CLAIMED

    # 验证 Run 状态已自动转为 RUNNING
    run_running = await store.get_run("run_1")
    assert run_running is not None
    assert run_running.status == RunStatus.RUNNING

    # 续约
    renewed = await store.renew_lease(
        segment_id="seg_1",
        fencing_token=1,
        lease_seconds=60.0,
    )
    assert renewed is True

    # 切片完成结算
    settled = await supervisor.complete_segment_and_advance(
        segment_id="seg_1",
        fencing_token=1,
        is_last_segment=True,
        final_output="Task finished",
    )
    assert settled is True

    # 验证最终状态
    final_run = await store.get_run("run_1")
    assert final_run is not None
    assert final_run.status == RunStatus.COMPLETED
    assert final_run.final_output == "Task finished"


@pytest.mark.asyncio
async def test_fencing_token_monotonically_increases_and_prevents_split_brain() -> None:
    """测试 Fencing Token 防脑裂机制，旧 Worker 的延迟写入被物理阻断。"""
    store = JobStore()
    await store.create_run(run_id="run_2", conversation_id="conv_2")
    await store.create_segment(segment_id="seg_2", run_id="run_2", sequence_index=0)

    # Worker 1 认领 (token=1)
    seg1 = await store.claim_next_segment(worker_id="worker_1", lease_seconds=1.0)
    assert seg1 is not None
    assert seg1.fencing_token == 1

    # 模拟 Worker 1 发生 GC 停顿或网络假死，Supervisor 重新将切片重置为 PENDING
    await store.reset_segment_to_pending(segment_id="seg_2", expected_fencing_token=1)

    # Worker 2 重新认领切片 (token=2)
    seg2 = await store.claim_next_segment(worker_id="worker_2", lease_seconds=60.0)
    assert seg2 is not None
    assert seg2.fencing_token == 2

    # Worker 1 苏醒，尝试使用陈旧的 token=1 续约或结算，必须被物理阻断
    stale_renew = await store.renew_lease(segment_id="seg_2", fencing_token=1, lease_seconds=60.0)
    assert stale_renew is False

    stale_settle = await store.settle_segment(
        segment_id="seg_2",
        fencing_token=1,
        status=SegmentStatus.COMPLETED,
    )
    assert stale_settle is False

    # Worker 2 正常结算 (token=2)
    valid_settle = await store.settle_segment(
        segment_id="seg_2",
        fencing_token=2,
        status=SegmentStatus.COMPLETED,
    )
    assert valid_settle is True


@pytest.mark.asyncio
async def test_lease_context_heartbeat_and_lost_fuse() -> None:
    """测试 LeaseContext 自动心跳续约与失联快速熔断机制。"""
    store = JobStore()
    await store.create_run(run_id="run_3", conversation_id="conv_3")
    await store.create_segment(segment_id="seg_3", run_id="run_3", sequence_index=0)

    seg = await store.claim_next_segment(worker_id="worker_3", lease_seconds=10.0)
    assert seg is not None

    # 验证当租约丢失时，不仅 is_lost 为 True，且退出上下文时必定触发 LeaseLostError 强行熔断
    with pytest.raises(LeaseLostError):
        async with LeaseContext(
            store=store,
            segment_id=seg.segment_id,
            fencing_token=seg.fencing_token,
            lease_seconds=5.0,
            interval_seconds=0.05,
        ) as lease:
            lease.check_alive()
            await asyncio.sleep(0.12)
            # 心跳已在后台完成至少一次续约
            lease.check_alive()

            # 模拟外部夺取了租约（自增 token）
            await store.reset_segment_to_pending(seg.segment_id, seg.fencing_token)
            await store.claim_next_segment(worker_id="worker_hijack", lease_seconds=10.0)

            # 等待下一次心跳周期触发失败
            await asyncio.sleep(0.12)
            assert lease.is_lost is True
            with pytest.raises(LeaseLostError):
                lease.check_alive()


@pytest.mark.asyncio
async def test_checkpoint_reconciler_four_level_evidence_actions() -> None:
    """测试四级现场求证对账自愈决策逻辑。"""
    store = JobStore()
    reconciler = CheckpointReconciler(store)

    # 1. RETRY_SAFE: 纯读/无副作用
    await store.create_run("run_safe", "conv_safe")
    await store.create_segment("seg_safe", "run_safe", 0)
    claimed_safe = await store.claim_next_segment("w1", 10.0, "run_safe")
    assert claimed_safe is not None
    await store.record_checkpoint(
        "seg_safe",
        claimed_safe.fencing_token,
        CheckpointEvidence(last_tool_name="web_search", has_side_effect=False),
    )
    updated_safe = await store.get_segment("seg_safe")
    assert updated_safe is not None
    action_1 = await reconciler.reconcile_expired_segment(updated_safe)
    assert action_1 == ReconciliationAction.RETRY_SAFE
    # 状态已重置为 PENDING 可重新调度
    recheck_safe = await store.get_segment("seg_safe")
    assert recheck_safe is not None and recheck_safe.status == SegmentStatus.PENDING

    # 2. RECONCILE_MESSAGE: 有外部消息凭据
    await store.create_run("run_msg", "conv_msg")
    await store.create_segment("seg_msg", "run_msg", 0)
    claimed_msg = await store.claim_next_segment("w2", 10.0, "run_msg")
    assert claimed_msg is not None
    await store.record_checkpoint(
        "seg_msg",
        claimed_msg.fencing_token,
        CheckpointEvidence(
            last_tool_name="send_email",
            has_side_effect=True,
            external_message_id="msg_9988",
        ),
    )
    updated_msg = await store.get_segment("seg_msg")
    assert updated_msg is not None
    action_2 = await reconciler.reconcile_expired_segment(updated_msg)
    assert action_2 == ReconciliationAction.RECONCILE_MESSAGE
    recheck_msg = await store.get_segment("seg_msg")
    assert recheck_msg is not None and recheck_msg.status == SegmentStatus.COMPLETED

    # 3. RESUME_FROM_EVIDENCE: 有中间状态持久化摘要
    await store.create_run("run_res", "conv_res")
    await store.create_segment("seg_res", "run_res", 0)
    claimed_res = await store.claim_next_segment("w3", 10.0, "run_res")
    assert claimed_res is not None
    await store.record_checkpoint(
        "seg_res",
        claimed_res.fencing_token,
        CheckpointEvidence(
            last_tool_name="write_file",
            has_side_effect=True,
            persisted_state_digest="sha256_checkpoint_123",
        ),
    )
    updated_res = await store.get_segment("seg_res")
    assert updated_res is not None
    action_3 = await reconciler.reconcile_expired_segment(updated_res)
    assert action_3 == ReconciliationAction.RESUME_FROM_EVIDENCE

    # 4. BLOCK_UNCERTAIN_SIDE_EFFECT: 黑盒写操作无凭证，必须阻断
    await store.create_run("run_blk", "conv_blk")
    await store.create_segment("seg_blk", "run_blk", 0)
    claimed_blk = await store.claim_next_segment("w4", 10.0, "run_blk")
    assert claimed_blk is not None
    await store.record_checkpoint(
        "seg_blk",
        claimed_blk.fencing_token,
        CheckpointEvidence(last_tool_name="pay_order", has_side_effect=True),
    )
    updated_blk = await store.get_segment("seg_blk")
    assert updated_blk is not None
    action_4 = await reconciler.reconcile_expired_segment(updated_blk)
    assert action_4 == ReconciliationAction.BLOCK_UNCERTAIN_SIDE_EFFECT
    # 验证 Run 被暂停待审批
    run_blk = await store.get_run("run_blk")
    assert run_blk is not None
    assert run_blk.status == RunStatus.PAUSED_FOR_APPROVAL


@pytest.mark.asyncio
async def test_inflight_input_queue_segment_boundary_ingestion() -> None:
    """测试切片边界原子提取飞入用户输入，避免破坏正在执行的思维链。"""
    store = JobStore()
    supervisor = JobSupervisor(store)
    await store.create_run("run_q", "conv_q")
    await store.create_segment("seg_q1", "run_q", 0)
    await store.create_segment("seg_q2", "run_q", 1)

    # 用户在运行中输入两条消息
    await store.enqueue_input("in_1", "run_q", "Please check item A")
    await store.enqueue_input("in_2", "run_q", "Also check item B")

    # 在切片 1 边界摄入
    claimed_inputs = await supervisor.ingest_inputs_at_boundary("run_q", "seg_q1")
    assert len(claimed_inputs) == 2
    assert claimed_inputs[0].status == InputStatus.CLAIMED

    # 切片 1 完成并标记输入已消费
    await supervisor.complete_segment_and_advance(
        segment_id="seg_q1",
        fencing_token=0,
        is_last_segment=False,
    )

    # 验证输入队列已无待处理消息
    next_inputs = await supervisor.ingest_inputs_at_boundary("run_q", "seg_q2")
    assert len(next_inputs) == 0


def test_atomic_segment_appender_and_step_budget() -> None:
    """测试 AtomicSegmentAppender 的 expectedTail 校验与步数预算守卫。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        log_file = Path(tmp_dir) / "segment_output.log"

        # 初始追加 (expected_tail 为空)
        AtomicSegmentAppender.append_with_tail_check(
            file_path=log_file,
            content="Line 1: init\r\n",
            expected_tail="",
        )
        assert log_file.read_text(encoding="utf-8") == "Line 1: init\n"

        # 正确期望追加
        AtomicSegmentAppender.append_with_tail_check(
            file_path=log_file,
            content="Line 2: step 1",
            expected_tail="Line 1: init\n",
        )
        assert "Line 2: step 1\n" in log_file.read_text(encoding="utf-8")

        # 期望不匹配时阻断追加
        with pytest.raises(TailMismatchError):
            AtomicSegmentAppender.append_with_tail_check(
                file_path=log_file,
                content="Line 3: conflict",
                expected_tail="Wrong tail content\n",
            )

    # 步数预算超额测试
    budget = BoundedSegmentBudget(max_steps=2)
    budget.advance_step()
    budget.advance_step()
    with pytest.raises(StepBudgetExceededError):
        budget.advance_step()


def test_cron_job_adapter_decision_matrix() -> None:
    """测试 CronJobAdapter 对 exit_code 和副作用的对账裁决矩阵。"""
    adapter = CronJobAdapter(max_consecutive_failures=2)

    # 1. 成功退出
    res_succ = adapter.evaluate_execution(exit_code=0, has_side_effect=False)
    assert res_succ.decision == CronExecutionDecision.SUCCESS

    # 2. 外部消息已确认的副作用任务
    res_msg = adapter.evaluate_execution(
        exit_code=1,
        has_side_effect=True,
        external_message_id="ext_tx_123",
    )
    assert res_msg.decision == CronExecutionDecision.SUCCESS

    # 3. 未求证副作用任务必须阻断并请求审批
    res_block = adapter.evaluate_execution(exit_code=1, has_side_effect=True)
    assert res_block.decision == CronExecutionDecision.BLOCK_UNCERTAIN_SIDE_EFFECT
    assert res_block.requires_approval is True

    # 4. 幂等安全重试
    res_retry = adapter.evaluate_execution(
        exit_code=1,
        has_side_effect=False,
        consecutive_failures=1,
    )
    assert res_retry.decision == CronExecutionDecision.RETRY_SAFE
    assert res_retry.can_retry_immediately is True

    # 5. 超出最大重试次数转终态失败
    res_term = adapter.evaluate_execution(
        exit_code=1,
        has_side_effect=False,
        consecutive_failures=2,
    )
    assert res_term.decision == CronExecutionDecision.TERMINAL_FAILURE
