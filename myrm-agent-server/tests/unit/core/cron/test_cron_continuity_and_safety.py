"""Cron 跨轮记忆连续性、免模型 0 Token 巡检去重与自规约防篡改安全护栏测试套件。

覆盖 BoundedScratchpad 有界记事本、ZeroTokenMonitorGovernor 噪声过滤与省流短路、
BotChatRouter 告警回写与防回环深度熔断、以及 SelfRuleIntegrityGuard 核心规约物理审批拦截。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
from myrm_agent_harness.security.self_rule_integrity_guard import (
    SelfRuleIntegrityGuard,
)
from myrm_agent_harness.toolkits.cron.continuity.scratchpad import (
    BoundedScratchpad,
    InvalidJobIdError,
)
from myrm_agent_harness.toolkits.cron.continuity.zero_token_governor import (
    ZeroTokenMonitorGovernor,
)
from myrm_agent_harness.toolkits.cron.routing.bot_chat_router import (
    BotChatRouter,
)


def test_bounded_scratchpad_save_load_and_atomic_replace() -> None:
    """测试 BoundedScratchpad 的常规读取、原子保存、1KB限制与环比上下文提示语。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        storage_dir = Path(tmp_dir)
        scratchpad = BoundedScratchpad(storage_dir)

        # 初始读取空状态
        assert scratchpad.load("job_daily_report") == {}
        assert scratchpad.format_continuity_context("job_daily_report") is None

        # 写入超长摘要与指标
        long_summary = "A" * 800  # 超出 500 限制
        metrics = {"error_count": "3", "p99_latency_ms": "120"}
        saved = scratchpad.save(
            job_id="job_daily_report",
            last_summary=long_summary,
            last_metrics=metrics,
        )
        assert saved is True

        # 读取并验证摘要被安全截断
        loaded = scratchpad.load("job_daily_report")
        assert len(loaded["last_summary"]) <= 500
        assert loaded["metric_error_count"] == "3"
        assert loaded["metric_p99_latency_ms"] == "120"

        # 验证提示语格式化
        context_prompt = scratchpad.format_continuity_context("job_daily_report")
        assert context_prompt is not None
        assert "[Previous Execution Memory]" in context_prompt
        assert "error_count: 3" in context_prompt

        # 测试文件损坏自愈：覆写为非 JSON
        file_path = storage_dir / "job_daily_report.scratchpad.json"
        file_path.write_text("corrupted{{{invalid_json", encoding="utf-8")
        healed = scratchpad.load("job_daily_report")
        assert healed == {}


def test_bounded_scratchpad_path_traversal_rejection() -> None:
    """测试 BoundedScratchpad 对目录遍历恶意标识符的严格清洗与拦截。"""
    with tempfile.TemporaryDirectory() as tmp_dir:
        scratchpad = BoundedScratchpad(Path(tmp_dir))

        malicious_ids = [
            "../../etc/passwd",
            "job/sub/123",
            "job name with spaces",
            "job$bad*char",
            "a" * 65,  # 超过 64 长度
        ]
        for bad_id in malicious_ids:
            with pytest.raises(InvalidJobIdError):
                scratchpad.load(bad_id)
            with pytest.raises(InvalidJobIdError):
                scratchpad.save(bad_id, last_summary="test")


def test_zero_token_governor_noise_stripping_and_skip_decision() -> None:
    """测试 ZeroTokenMonitorGovernor 的动态噪声过滤与 0 Token 免模型短路。"""
    governor = ZeroTokenMonitorGovernor()

    # 首次执行：建立基线哈希，必须正常调用模型
    payload_run_1 = '{"status": "UP", "timestamp": "2026-10-18T00:00:01Z", "trace_id": "tx_1"}'
    decision_1 = governor.evaluate(
        current_payload=payload_run_1,
        previous_hash=None,
        is_quiet_mode=True,
    )
    assert decision_1.can_skip_model is False
    assert decision_1.action == "PROCEED_MODEL"
    base_hash = decision_1.new_hash

    # 第二次执行：仅时间戳和 trace_id 变了，业务数据 "status": "UP" 完全没变
    payload_run_2 = '{"timestamp": "2026-10-18T00:05:00Z", "trace_id": "tx_2", "status": "UP"}'
    decision_2 = governor.evaluate(
        current_payload=payload_run_2,
        previous_hash=base_hash,
        is_quiet_mode=True,
    )
    assert decision_2.can_skip_model is True
    assert decision_2.action == "0_TOKEN_SKIPPED"
    assert decision_2.new_hash == base_hash

    # 第三次执行：业务数据发生变化
    payload_run_3 = '{"status": "DEGRADED", "timestamp": "2026-10-18T00:10:00Z"}'
    decision_3 = governor.evaluate(
        current_payload=payload_run_3,
        previous_hash=base_hash,
        is_quiet_mode=True,
    )
    assert decision_3.can_skip_model is False
    assert decision_3.action == "PROCEED_MODEL"
    assert decision_3.new_hash != base_hash


def test_zero_token_governor_large_payload_streaming() -> None:
    """测试 ZeroTokenMonitorGovernor 对超大载荷走分块流式计算，杜绝 OOM。"""
    governor = ZeroTokenMonitorGovernor(max_payload_bytes=1024)  # 调低测试门槛至 1KB
    large_payload = "X" * 2048

    h1 = governor.compute_canonical_hash(large_payload)
    h2 = governor.compute_canonical_hash(large_payload)
    assert h1 == h2
    assert len(h1) == 64


def test_bot_chat_router_dispatch_and_cascade_block() -> None:
    """测试 BotChatRouter 告警投递、深度熔断与平滑降级。"""
    router = BotChatRouter(registered_bot_ids=["devops_bot", "sre_bot"])

    # 1. 成功投递至已注册 Bot
    res_ok = router.route_alert_to_bot(
        origin_cron_id="cron_cluster_check",
        target_agent_id="devops_bot",
        alert_content="Pod memory usage exceeded 90%",
        call_depth=0,
    )
    assert res_ok.success is True
    assert res_ok.action == "ROUTED_TO_BOT_CHAT"
    assert res_ok.message_id is not None

    # 2. 深度熔断（call_depth >= 1）：阻断级联死锁
    res_cascade = router.route_alert_to_bot(
        origin_cron_id="cron_cluster_check",
        target_agent_id="devops_bot",
        alert_content="Followup alert",
        call_depth=1,
    )
    assert res_cascade.success is False
    assert res_cascade.action == "CASCADE_BLOCKED"

    # 3. 目标 Bot 未注册时平滑降级
    res_fallback = router.route_alert_to_bot(
        origin_cron_id="cron_cluster_check",
        target_agent_id="non_existent_bot",
        alert_content="Cluster alert",
        call_depth=0,
    )
    assert res_fallback.success is False
    assert res_fallback.action == "FALLBACK_DEFAULT_CHANNEL"


def test_self_rule_integrity_guard_nt_namespace_and_core_rules() -> None:
    """测试 SelfRuleIntegrityGuard Windows NT 拦截、全小写穿透与核心规约强审批。"""
    guard = SelfRuleIntegrityGuard()

    # 1. Windows NT 命名空间预检硬阻断
    nt_paths = [
        "\\??\\UNC\\attacker.example\\share\\x",
        "\\\\.\\PhysicalDrive0",
        "\\\\?\\UNC\\remote_host\\file",
    ]
    for nt_path in nt_paths:
        verdict = guard.inspect_write_target(nt_path)
        assert verdict.is_denied is True
        assert verdict.verdict == "HARD_DENY"

    # 2. 核心规约文件与大小写变体拦截（需物理人类审批）
    protected_cases = [
        "AGENTS.md",
        "agents.md",
        "Agents.Md",
        "agents2.md",
        ".env",
        ".env.production",
        "memory.db",
        "skills/creative/summary.py",
        "/etc/project/skills/tool.py",
    ]
    for p in protected_cases:
        verdict = guard.inspect_write_target(p)
        assert verdict.is_denied is False
        assert verdict.requires_approval is True
        assert verdict.verdict == "REQUIRES_APPROVAL"

    # 3. 普通开发文件安全放行
    safe_cases = [
        "README.md",
        "src/app/main.py",
        "tests/test_demo.py",
        "docs/architecture.txt",
    ]
    for safe in safe_cases:
        verdict = guard.inspect_write_target(safe)
        assert verdict.is_denied is False
        assert verdict.requires_approval is False
        assert verdict.verdict == "ALLOW"
