"""Shared fixtures' building blocks for the chat disposal tests."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver, empty_checkpoint
from langgraph.checkpoint.memory import MemorySaver
from myrm_agent_harness.agent.security.approval_flow import AllowlistEntry, get_allowlist

from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.chat import chat_disposal

CHAT_ID = "chat-disposal-1"
SANDBOX_ROOT = "/tmp/myrm-test-sandbox"
SANDBOX_DIR = f"{SANDBOX_ROOT}/{CHAT_ID}"
OWNER = "sandbox"


@dataclass
class Spies:
    runtime_pool: AsyncMock
    execution_cache: AsyncMock
    memory_purge: AsyncMock
    retry_queue: AsyncMock
    worktree: AsyncMock
    workspace: AsyncMock
    ephemeral_delta: MagicMock


def install_spies(monkeypatch: pytest.MonkeyPatch) -> Spies:
    """Replace the slow collaborators of the disposal steps with recorders."""
    recorded = Spies(
        runtime_pool=AsyncMock(),
        execution_cache=AsyncMock(),
        memory_purge=AsyncMock(return_value={}),
        retry_queue=AsyncMock(),
        worktree=AsyncMock(return_value=True),
        workspace=AsyncMock(return_value={}),
        ephemeral_delta=MagicMock(),
    )
    monkeypatch.setattr(chat_disposal, "close_external_agent_pool_for_chat", recorded.runtime_pool)
    monkeypatch.setattr(chat_disposal, "close_execution_cache_for_chat_all_agents", recorded.execution_cache)
    manager = MagicMock(purge_by_source_chat_id=recorded.memory_purge)
    monkeypatch.setattr("app.core.memory.get_cascade_memory_manager", AsyncMock(return_value=manager))
    monkeypatch.setattr("app.services.memory.extract_retry.extract_retry_queue.clear_for_chat", recorded.retry_queue)
    monkeypatch.setattr("app.services.chat.sandbox_worktree.cleanup_sandbox_worktree", recorded.worktree)
    monkeypatch.setattr("app.services.infra.sandbox_cleanup.cleanup_chat_workspaces", recorded.workspace)
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.memory.ephemeral_delta.notify.clear_ephemeral_deltas_for_session",
        recorded.ephemeral_delta,
    )
    return recorded


def point_event_log_at_scratch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the event log at a scratch directory so no test reads or deletes the real one."""
    log_dir = tmp_path / "event_logs"
    log_dir.mkdir()
    monkeypatch.setattr("app.config.settings.settings.database.event_log_dir", str(log_dir))
    return log_dir


def write_event_log(log_dir: Path, session_id: str) -> Path:
    path = log_dir / f"{session_id}.jsonl"
    path.write_text('{"event_type": "llm_request", "data": {"prompt_preview": "[user] secret"}}\n', encoding="utf-8")
    return path


@asynccontextmanager
async def installed_checkpointer() -> AsyncIterator[BaseCheckpointSaver[str]]:
    saver = MemorySaver()
    set_checkpointer(saver)
    try:
        yield saver
    finally:
        _reset_checkpointer_for_testing()
        await get_allowlist().clear_session(OWNER, CHAT_ID)


async def _seed_checkpoint(saver: BaseCheckpointSaver[str], thread_id: str) -> None:
    checkpoint = empty_checkpoint()
    checkpoint["channel_values"] = {"messages": [HumanMessage("question"), AIMessage("answer")]}
    await saver.aput(
        {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
        checkpoint,
        {"source": "test", "step": 0, "parents": {}},
        {},
    )


async def grant_and_checkpoint(saver: BaseCheckpointSaver[str]) -> None:
    for thread_id in (CHAT_ID, f"chat_{CHAT_ID}"):
        await _seed_checkpoint(saver, thread_id)
    await get_allowlist().add(OWNER, AllowlistEntry(permission="shell_exec", tool_name="bash", session_id=CHAT_ID))


async def is_stored(saver: BaseCheckpointSaver[str], thread_id: str) -> bool:
    return await saver.aget_tuple({"configurable": {"thread_id": thread_id}}) is not None


def is_granted() -> bool:
    return get_allowlist().check(OWNER, "shell_exec", "bash", session_id=CHAT_ID)
