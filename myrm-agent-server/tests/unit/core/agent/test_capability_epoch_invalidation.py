"""智能体能力纪元哈希计算与回合边界 JIT 缓存失效自动化测试套件。

覆盖纯净要素哈希幂等性、要素变更敏感性、稳态 O(1) 快速命中、
JIT 增量热重编译、双重检查锁并发防竞态与运行时诚实性元数据打标。
"""

from __future__ import annotations

import asyncio

import pytest
from myrm_agent_harness.agent.capability.epoch_hasher import (
    CanonicalCapabilityManifest,
    CapabilityEpochHasher,
)
from myrm_agent_harness.agent.capability.session_invalidator import (
    SessionCapabilityState,
    TurnBoundaryEpochValidator,
)


def test_capability_epoch_hasher_purity_and_determinism() -> None:
    """测试 CapabilityEpochHasher 的格式规范、换行归一化与乱序排序幂等性。"""
    manifest_1 = CanonicalCapabilityManifest(
        system_prompt="  You are a senior architect.\r\nFollow PEP8.\n  ",
        skills=("code_search", "git_blame"),
        tools=("bash", "write_file", "view_file"),
        mcp_servers=("filesystem", "sqlite"),
        model_id="gpt-4o",
        reasoning_effort="high",
        temperature=0.7,
        soul_content="Be rigorous and direct.\r\n",
    )

    manifest_2 = CanonicalCapabilityManifest(
        system_prompt="You are a senior architect.\nFollow PEP8.",
        skills=("git_blame", "code_search"),  # 逆序
        tools=("view_file", "bash", "write_file"),  # 乱序
        mcp_servers=("sqlite", "filesystem"),  # 逆序
        model_id="gpt-4o",
        reasoning_effort="high",
        temperature=0.7,
        soul_content="Be rigorous and direct.",
    )

    epoch_1 = CapabilityEpochHasher.calculate_epoch(manifest_1)
    epoch_2 = CapabilityEpochHasher.calculate_epoch(manifest_2)

    assert epoch_1.startswith("ep-")
    assert len(epoch_1) == 11  # 'ep-' + 8 字符 hex
    assert epoch_1 == epoch_2, "Epoch calculation must be order-independent and whitespace-normalized"


def test_capability_epoch_changes_on_any_core_manifest_change() -> None:
    """测试当 6 大核心静态能力要素发生任何一项微调时，Epoch 均发生精确改变。"""
    base = CanonicalCapabilityManifest(
        system_prompt="Base prompt",
        skills=("skill_a",),
        tools=("tool_a",),
        mcp_servers=("mcp_a",),
        model_id="base_model",
        reasoning_effort="medium",
        temperature=0.5,
        soul_content="Base soul",
    )
    base_epoch = CapabilityEpochHasher.calculate_epoch(base)

    mutations = [
        CanonicalCapabilityManifest(system_prompt="Modified prompt", skills=base.skills, tools=base.tools, mcp_servers=base.mcp_servers, model_id=base.model_id, reasoning_effort=base.reasoning_effort, temperature=base.temperature, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=("skill_a", "skill_b"), tools=base.tools, mcp_servers=base.mcp_servers, model_id=base.model_id, reasoning_effort=base.reasoning_effort, temperature=base.temperature, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=base.skills, tools=("tool_a", "tool_b"), mcp_servers=base.mcp_servers, model_id=base.model_id, reasoning_effort=base.reasoning_effort, temperature=base.temperature, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=base.skills, tools=base.tools, mcp_servers=("mcp_b",), model_id=base.model_id, reasoning_effort=base.reasoning_effort, temperature=base.temperature, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=base.skills, tools=base.tools, mcp_servers=base.mcp_servers, model_id="claude-3-7-sonnet", reasoning_effort=base.reasoning_effort, temperature=base.temperature, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=base.skills, tools=base.tools, mcp_servers=base.mcp_servers, model_id=base.model_id, reasoning_effort="high", temperature=base.temperature, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=base.skills, tools=base.tools, mcp_servers=base.mcp_servers, model_id=base.model_id, reasoning_effort=base.reasoning_effort, temperature=0.9, soul_content=base.soul_content),
        CanonicalCapabilityManifest(system_prompt=base.system_prompt, skills=base.skills, tools=base.tools, mcp_servers=base.mcp_servers, model_id=base.model_id, reasoning_effort=base.reasoning_effort, temperature=base.temperature, soul_content="New soul personality"),
    ]

    for mutated in mutations:
        mutated_epoch = CapabilityEpochHasher.calculate_epoch(mutated)
        assert mutated_epoch != base_epoch, "Epoch must change when any capability element mutates"


@pytest.mark.asyncio
async def test_turn_boundary_epoch_validator_fast_path_and_rebuild() -> None:
    """测试 TurnBoundaryEpochValidator 的首次编译、稳态快速命中与配置热变更 JIT 生效。"""
    session = SessionCapabilityState(session_id="conv_101", agent_id="agent_architect")

    manifest_v1 = CanonicalCapabilityManifest(
        system_prompt="You are v1.",
        tools=("view_file",),
        model_id="gpt-4o",
    )

    # 1. 首次调用：触发初始 JIT 编译
    res_init = await TurnBoundaryEpochValidator.validate_and_rebuild_if_stale(
        session_state=session,
        latest_manifest=manifest_v1,
    )
    assert res_init.is_rebuilt is True
    assert session.cached_epoch == res_init.current_epoch
    assert "You are v1." in res_init.context.system_prompt
    assert res_init.context.available_tools == ("view_file",)

    # 2. 稳态复用：相同配置再次进入，Fast-Path O(1) 命中，零重构
    res_steady = await TurnBoundaryEpochValidator.validate_and_rebuild_if_stale(
        session_state=session,
        latest_manifest=manifest_v1,
    )
    assert res_steady.is_rebuilt is False
    assert res_steady.current_epoch == res_init.current_epoch
    assert res_steady.context is res_init.context  # 内存对象指针完全复用

    # 3. 配置热变更：修改了 Prompt 并新增了工具
    manifest_v2 = CanonicalCapabilityManifest(
        system_prompt="You are v2 with advanced tools.",
        tools=("view_file", "write_file"),
        model_id="gpt-4o",
    )

    res_hot = await TurnBoundaryEpochValidator.validate_and_rebuild_if_stale(
        session_state=session,
        latest_manifest=manifest_v2,
    )
    assert res_hot.is_rebuilt is True
    assert res_hot.current_epoch != res_init.current_epoch
    assert session.cached_epoch == res_hot.current_epoch
    assert "You are v2 with advanced tools." in res_hot.context.system_prompt
    assert res_hot.context.available_tools == ("view_file", "write_file")


@pytest.mark.asyncio
async def test_double_checked_locking_concurrent_rebuild() -> None:
    """测试多协程并发请求触发 JIT 校验时，双重检查锁定保障只编译一次。"""
    session = SessionCapabilityState(session_id="conv_concurrent", agent_id="agent_fast")
    manifest = CanonicalCapabilityManifest(
        system_prompt="Concurrent prompt.",
        tools=("bash",),
    )

    # 模拟 10 个并发请求同时涌入
    tasks = [
        TurnBoundaryEpochValidator.validate_and_rebuild_if_stale(
            session_state=session,
            latest_manifest=manifest,
        )
        for _ in range(10)
    ]
    results = await asyncio.gather(*tasks)

    # 验证所有请求获得的 Epoch 与上下文快照完全一致
    epochs = {r.current_epoch for r in results}
    assert len(epochs) == 1

    # 验证仅有且只有 1 个请求真正执行了重建（is_rebuilt=True），其余均复用
    rebuilt_count = sum(1 for r in results if r.is_rebuilt)
    assert rebuilt_count == 1, "Double-checked locking must ensure exactly one JIT rebuild execution"


def test_runtime_honesty_metadata_stamping() -> None:
    """测试 CompiledAgentContext 的元数据指纹与运行时诚实性。"""
    manifest = CanonicalCapabilityManifest(
        system_prompt="Honest agent.",
        model_id="deepseek-r1",
        reasoning_effort="high",
        temperature=0.6,
    )
    epoch = CapabilityEpochHasher.calculate_epoch(manifest)
    context = TurnBoundaryEpochValidator.build_context_from_manifest(manifest, epoch)

    assert context.capability_epoch == epoch
    assert context.model_id == "deepseek-r1"
    assert context.reasoning_effort == "high"
    assert context.temperature == 0.6
    assert context.created_at_mono > 0.0
