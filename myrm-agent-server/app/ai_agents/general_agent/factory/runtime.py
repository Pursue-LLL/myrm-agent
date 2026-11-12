"""[INPUT]
- myrm_agent_harness.agent.context_management.archive_checkpoint.store::ArchiveCheckpointStore (POS: Archive checkpoint persistence via EpisodicMemory.)
- myrm_agent_harness.agent.context_management.archive_checkpoint.summary_service::ArchiveCheckpointNotifier (POS: Async lite-LLM archive summary scheduling.)
- myrm_agent_harness.agent.context_management.infra.schemas::ContextCompressEvictionCallback / ContextCompressOffloadCallback / ContextSnapshotCallback (POS: Context management shared data structures. Defines compact format types, summary schemas, and configuration constants as)
- myrm_agent_harness.agent.context_management.infra.schemas_pre_compact::ContextPreCompactCallback (POS: Context management pre-compaction interception schemas. Defines the three-state control contract (Cancel / Replace / Passthrough) and semantic injection types for pipeline processors.)
- myrm_agent_harness.toolkits.code_execution.executors.base::CodeExecutor (POS: Code executor base classes.)
- myrm_agent_harness.toolkits.memory.manager::MemoryManager (POS: Stable public import path for the memory toolkit façade.)
- app.ai_agents.extensions::ArchiveCheckpointMemoryExtension / PreCompactMemoryExtension / ZeroCostMemoryExtension / ArchiveCheckpointMemoryExtension / PreCompactMemoryExtension / ZeroCostMemoryExtension (POS: app.ai_agents.extensions)
- app.ai_agents.general_agent.agent::GeneralAgent (POS: 通用 Agent 核心实现。管理 Agent 生命周期（初始化、流式执行、资源释放）， 工具创建委托给 ToolSetupMixin。)
- myrm_agent_harness.toolkits.code_execution.factory::create_executor (POS: Code executor factory. Creates LocalExecutor for in-container code execution based on configuration.)
- app.ai_agents.general_agent.config_builders::build_execution_config (POS: Config builders for General Agent)
- myrm_agent_harness.runtime.context.offload::create_compress_offload_callback / create_context_snapshot_callback (POS: Context offload: persist full tool outputs and conversation snapshots to persistent volume.)
- app.platform_utils::get_quota_manager (POS: 平台适配层)
- app.services.agent.outbound_notify.factory_wiring::append_channel_notify_tool (POS: Single SSOT for `general_agent/factory/` and integration tests — avoids duplicated wiring logic.)
- myrm_agent_harness.toolkits.code_execution.interceptor::set_execution_interceptor (POS: Seam between the code-execution toolkit and a host that wants to snapshot or audit actions.)
- app.services.checkpoint.snapshot_service::get_snapshot_interceptor (POS: Server-layer snapshot interceptor. Handles per-turn dedup, SSE events, and multi-agent metadata binding.)
- myrm_agent_harness.toolkits.memory.strategies.extraction_domain::auto_detect_preset (POS: Domain extraction preset data and prompt section builder for the memory extractor.)

[OUTPUT]
- SandboxRuntime: SandboxRuntime
- load_channel_notify_tool: load_channel_notify_tool
- build_sandbox_runtime: build_sandbox_runtime

[POS]
装配第三阶段；只创建执行资源，不组装中间件或提示词。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from langchain_core.language_models import BaseChatModel
    from myrm_agent_harness.agent.context_management.archive_checkpoint.store import (
        ArchiveCheckpointStore,
    )
    from myrm_agent_harness.agent.context_management.archive_checkpoint.summary_service import (
        ArchiveCheckpointNotifier,
    )
    from myrm_agent_harness.agent.context_management.infra.schemas import (
        ContextCompressEvictionCallback,
        ContextCompressOffloadCallback,
        ContextSnapshotCallback,
    )
    from myrm_agent_harness.agent.context_management.infra.schemas_pre_compact import (
        ContextPreCompactCallback,
    )
    from myrm_agent_harness.toolkits.code_execution.executors.base import CodeExecutor
    from myrm_agent_harness.toolkits.memory.manager import MemoryManager

    from app.ai_agents.extensions import (
        ArchiveCheckpointMemoryExtension,
        PreCompactMemoryExtension,
        ZeroCostMemoryExtension,
    )
    from app.ai_agents.general_agent.agent import GeneralAgent

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SandboxRuntime:
    executor: "CodeExecutor"
    compress_offload_cb: "ContextCompressOffloadCallback"
    context_snapshot_cb: "ContextSnapshotCallback"
    compress_eviction_cb: "ContextCompressEvictionCallback | None"
    pre_compact_cb: "ContextPreCompactCallback | None"
    archive_checkpoint_store: "ArchiveCheckpointStore | None"
    archive_checkpoint_notifier: "ArchiveCheckpointNotifier | None"
    memory_ext: "ZeroCostMemoryExtension"
    pre_compact_ext: "PreCompactMemoryExtension"
    archive_checkpoint_ext: "ArchiveCheckpointMemoryExtension"


def load_channel_notify_tool(agent_wrapper: "GeneralAgent", tools: list[object]) -> bool:
    channel_notify_tool_loaded = False
    try:
        from app.services.agent.outbound_notify.factory_wiring import (
            append_channel_notify_tool,
        )

        target_count = append_channel_notify_tool(
            agent_wrapper.notify_targets,
            tools,
            allowed_roots=agent_wrapper.declared_allowed_roots,
            is_readonly=getattr(agent_wrapper, "is_readonly", False),
        )
        if target_count:
            channel_notify_tool_loaded = True
            logger.info(
                "Loaded channel_notify_tool (%d targets) [Turn1]",
                target_count,
            )
    except Exception as e:
        logger.warning("channel_notify_tool load failed (degraded): %s", e)

    return channel_notify_tool_loaded


async def build_sandbox_runtime(
    agent_wrapper: "GeneralAgent",
    *,
    llm: "BaseChatModel",
    memory_manager: "MemoryManager | None",
    effective_chat_id: str,
    workspace_root: str | None,
) -> SandboxRuntime:
    from myrm_agent_harness.toolkits.code_execution.factory import create_executor

    from ..config_builders import build_execution_config

    exec_config = build_execution_config(agent_wrapper.code_execution_allow_network)
    executor = create_executor(exec_config)
    if workspace_root:
        executor.bind_workspace(workspace_root)

    logger.info(f"创建沙箱执行器: {executor.get_executor_name()}")
    agent_wrapper._executor = executor

    # Register the workspace snapshot interceptor for WebUI main conversations.
    # ChannelExecutor already registers it via app.core.channel_bridge.agent_executor;
    # this idempotent call covers the main-conversation path so FileSnapshotPanel
    # shows turn-level snapshots for WebUI users too.
    try:
        from myrm_agent_harness.toolkits.code_execution.interceptor import (
            set_execution_interceptor,
        )

        from app.services.checkpoint.snapshot_service import (
            get_snapshot_interceptor,
        )

        set_execution_interceptor(get_snapshot_interceptor())
    except Exception as e:
        logger.warning("Failed to register snapshot interceptor: %s", e)

    from myrm_agent_harness.runtime.context.offload import (
        create_compress_offload_callback,
        create_context_snapshot_callback,
    )

    from app.platform_utils import get_quota_manager

    quota_manager = await get_quota_manager()
    compress_offload_cb = create_compress_offload_callback(
        executor,
        quota_checker=quota_manager,
    )
    context_snapshot_cb = create_context_snapshot_callback(
        executor,
        quota_checker=quota_manager,
    )

    from app.ai_agents.extensions import (
        ArchiveCheckpointMemoryExtension,
        PreCompactMemoryExtension,
        ZeroCostMemoryExtension,
    )

    extraction_preset = agent_wrapper.memory_extraction_preset
    if extraction_preset == "auto":
        from myrm_agent_harness.toolkits.memory.strategies.extraction_domain import (
            auto_detect_preset,
        )

        extraction_preset = auto_detect_preset(agent_wrapper.user_instructions or "").value

    is_sandbox = (
        agent_wrapper.enable_shell_tools
        or agent_wrapper.enable_external_cli
        or any(
            c in (getattr(agent_wrapper, "declared_capabilities", None) or ())
            for c in ("sandbox", "code_execution", "terminal", "coding")
        )
    )

    memory_ext = ZeroCostMemoryExtension(
        enable_memory_auto_extraction=agent_wrapper.enable_memory_auto_extraction,
        is_subagent=getattr(agent_wrapper, "is_subagent", False),
        channel_name=agent_wrapper.channel_name,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
        extractor_llm=agent_wrapper._lite_llm or llm,
        memory_extraction_preset=extraction_preset,
        is_sandbox_capable=is_sandbox,
    )
    compress_eviction_cb = memory_ext.build_eviction_callback()

    pre_compact_ext = PreCompactMemoryExtension(
        enabled=agent_wrapper.enable_memory,
        is_subagent=getattr(agent_wrapper, "is_subagent", False),
        channel_name=agent_wrapper.channel_name,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
    )
    pre_compact_cb = pre_compact_ext.build_pre_compact_callback()

    archive_checkpoint_ext = ArchiveCheckpointMemoryExtension(
        enabled=agent_wrapper.enable_memory and not agent_wrapper.incognito_mode,
        is_subagent=getattr(agent_wrapper, "is_subagent", False),
        channel_name=agent_wrapper.channel_name,
        memory_manager=memory_manager,
        effective_chat_id=effective_chat_id,
    )
    archive_checkpoint_store = archive_checkpoint_ext.build_archive_checkpoint_store()
    archive_checkpoint_notifier = archive_checkpoint_ext.build_archive_checkpoint_notifier()

    return SandboxRuntime(
        executor=executor,
        compress_offload_cb=compress_offload_cb,
        context_snapshot_cb=context_snapshot_cb,
        compress_eviction_cb=compress_eviction_cb,
        pre_compact_cb=pre_compact_cb,
        archive_checkpoint_store=archive_checkpoint_store,
        archive_checkpoint_notifier=archive_checkpoint_notifier,
        memory_ext=memory_ext,
        pre_compact_ext=pre_compact_ext,
        archive_checkpoint_ext=archive_checkpoint_ext,
    )
