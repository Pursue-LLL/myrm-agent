"""A read-only child spawned through `SubagentManager.spawn_child` never holds more than READ.

`delegate_task` and the verifier round bind a handle before they spawn. Dynamic workflow and every
other caller of `spawn_child` bind none, so a read-only child there would reach the file and shell
executors with no handle at all. The manager supplies that floor. The spawn, the child run and the
file executor are real; only the model is scripted.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.tools import BaseTool

from myrm_agent_harness.agent.base_agent import BaseAgent
from myrm_agent_harness.agent.meta_tools.file_ops.file_read_tool import create_file_read_tool
from myrm_agent_harness.agent.meta_tools.file_ops.file_write_tool import create_file_write_tool
from myrm_agent_harness.agent.sub_agents.manager import SubagentManager
from myrm_agent_harness.agent.sub_agents.spawn_capability import derive_spawn_capability, derive_verifier_capability
from myrm_agent_harness.agent.sub_agents.spawn_prep import apply_readonly_to_config, coerce_spawn_readonly
from myrm_agent_harness.agent.sub_agents.types import SubagentConfig, SubAgentResult, SubAgentStatus
from myrm_agent_harness.agent.types import WorkspaceBinding
from myrm_agent_harness.core.security.ocap import (
    AttenuationError,
    CapabilityAction,
    CapabilityHandle,
    capability_scope,
    get_current_capability,
    sign_capability_handle,
)
from myrm_agent_harness.toolkits.code_execution import create_executor


class _ScriptedModel(FakeMessagesListChatModel):
    def bind_tools(self, tools: object, **kwargs: object) -> _ScriptedModel:
        return self


def _tool_script(tool_name: str, args: dict[str, object]) -> list[BaseMessage]:
    call = {"name": tool_name, "args": args, "id": "call_1"}
    return [AIMessage(content="", tool_calls=[call]), AIMessage(content="finished")]


def _handle(workspace: Path, *, readonly: bool) -> CapabilityHandle:
    """The handle `delegate_task` would hold when it spawns from `workspace`."""
    return derive_spawn_capability(
        parent_agent=SimpleNamespace(_last_context={"workspace_path": str(workspace)}),
        agent_type="parent",
        readonly=readonly,
    )


def _expired(handle: CapabilityHandle) -> CapabilityHandle:
    unsigned = replace(handle, expires_at=handle.issued_at - 1.0, signature="")
    return replace(unsigned, signature=sign_capability_handle(unsigned))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = (tmp_path / "project").resolve()
    root.mkdir()
    (root / "report.txt").write_text("the parent's file", encoding="utf-8")
    return root


@pytest.fixture
def manager(workspace: Path) -> SubagentManager:
    parent = MagicMock()
    parent.trigger_async_wakeup = AsyncMock()
    parent._last_context = {"workspace_path": str(workspace)}
    with patch("myrm_agent_harness.agent.hooks.graceful_shutdown.get_shutdown_manager", return_value=MagicMock()):
        return SubagentManager(parent_agent=parent)


_RunChild = Callable[..., Awaitable[SubAgentResult]]


def _result(task_id: str, agent_type: str) -> SubAgentResult:
    return SubAgentResult(
        success=True,
        task_id=task_id,
        agent_type=agent_type,
        result="done",
        completed_at=time.time(),
        status=SubAgentStatus.COMPLETED,
    )


async def _spawn(
    manager: SubagentManager,
    run_child: _RunChild,
    *,
    config: SubagentConfig,
    wait: bool = True,
) -> SubAgentResult | dict[str, object]:
    """Spawn one child whose run is `run_child`, and let a detached child finish."""
    with patch.object(manager, "_run_subagent", run_child):
        outcome = await manager.spawn_child(
            task_id="child_1",
            agent_type="explorer",
            task_description="inspect the project",
            config=config,
            context={},
            tool_registry_getter=list,
            wait=wait,
            internal=True,
        )
        await asyncio.gather(*manager.children.values())
    return outcome


def _readonly_config() -> SubagentConfig:
    return apply_readonly_to_config(SubagentConfig(system_prompt="explorer"), True)


def _scripted_run(
    workspace: Path, storage_root: Path, tool: BaseTool, script: list[BaseMessage], events: list[str]
) -> _RunChild:
    """A child run that drives a real `BaseAgent` with `tool`, under whatever handle the spawn left bound."""

    async def run_child(*, task_id: str, agent_type: str, **_: object) -> SubAgentResult:
        agent = BaseAgent(llm=_ScriptedModel(responses=script), executor=create_executor(), tools=[tool])
        run_context: dict[str, object] = {
            "workspaces_storage_root": str(storage_root),
            "session_id": "chat_readonly_floor",
            "workspace_binding": WorkspaceBinding(mode="chat", root_path=str(workspace), chat_id="readonly_floor"),
            "workspace_path": str(workspace),
        }
        async for event in agent.run("inspect", context=run_context):
            events.append(str(event))
        return _result(task_id, agent_type)

    return run_child


def _recording_run(seen: list[CapabilityHandle | None]) -> _RunChild:
    async def run_child(*, task_id: str, agent_type: str, **_: object) -> SubAgentResult:
        seen.append(get_current_capability())
        return _result(task_id, agent_type)

    return run_child


@pytest.fixture
def storage_root(tmp_path: Path) -> Path:
    storage = (tmp_path / "storage").resolve()
    storage.mkdir()
    return storage


@pytest.mark.parametrize("wait", [True, False], ids=["awaited", "detached"])
async def test_readonly_child_spawned_through_the_manager_cannot_write(
    wait: bool, manager: SubagentManager, workspace: Path, storage_root: Path
) -> None:
    events: list[str] = []
    script = _tool_script("file_write_tool", {"path": "escaped.txt", "content": "x"})
    run_child = _scripted_run(workspace, storage_root, create_file_write_tool(), script, events)

    await _spawn(manager, run_child, config=_readonly_config(), wait=wait)

    assert not (workspace / "escaped.txt").exists()
    assert "denied by capability" in "\n".join(events)


async def test_readonly_child_spawned_through_the_manager_can_still_read(
    manager: SubagentManager, workspace: Path, storage_root: Path
) -> None:
    events: list[str] = []
    script = _tool_script("file_read_tool", {"paths": ["report.txt"]})
    run_child = _scripted_run(workspace, storage_root, create_file_read_tool(), script, events)

    await _spawn(manager, run_child, config=_readonly_config())

    joined = "\n".join(events)
    assert "'action_type': 'read'" in joined
    assert "denied by capability" not in joined


async def test_writable_child_spawned_through_the_manager_binds_no_handle(manager: SubagentManager) -> None:
    seen: list[CapabilityHandle | None] = []

    await _spawn(manager, _recording_run(seen), config=SubagentConfig(system_prompt="worker"))

    assert seen == [None]


async def test_readonly_spawn_keeps_the_handle_its_caller_already_bound(
    manager: SubagentManager, workspace: Path
) -> None:
    """`delegate_task` binds a workspace-scoped READ handle; the floor must not replace it."""
    seen: list[CapabilityHandle | None] = []
    bound = _handle(workspace, readonly=True)

    with capability_scope(bound):
        await _spawn(manager, _recording_run(seen), config=_readonly_config())

    assert seen == [bound]


async def test_readonly_spawn_keeps_a_verifiers_handle(manager: SubagentManager, workspace: Path) -> None:
    """A verifier runs commands; its READ+EXECUTE handle must survive a read-only config."""
    seen: list[CapabilityHandle | None] = []

    with capability_scope(_handle(workspace, readonly=False)):
        verifier = derive_verifier_capability("reviewer")
        with capability_scope(verifier):
            await _spawn(manager, _recording_run(seen), config=_readonly_config())

    assert seen == [verifier]


async def test_readonly_spawn_under_a_writing_parent_cannot_write_or_execute(
    manager: SubagentManager, workspace: Path
) -> None:
    seen: list[CapabilityHandle | None] = []
    writer = _handle(workspace, readonly=False)

    with capability_scope(writer):
        await _spawn(manager, _recording_run(seen), config=_readonly_config())

    (child_handle,) = seen
    assert child_handle is not None
    assert child_handle.actions == {CapabilityAction.READ}
    assert child_handle.scope == writer.scope


async def test_readonly_spawn_under_an_expired_parent_handle_does_not_start_a_child(
    manager: SubagentManager, workspace: Path
) -> None:
    seen: list[CapabilityHandle | None] = []

    with capability_scope(_expired(_handle(workspace, readonly=False))):
        outcome = await _spawn(manager, _recording_run(seen), config=_readonly_config())

    assert isinstance(outcome, SubAgentResult)
    assert outcome.success is False
    assert seen == []
    assert not manager.children


def test_readonly_capability_without_a_parent_handle_reads_anywhere_and_changes_nothing() -> None:
    from myrm_agent_harness.agent.sub_agents.spawn_capability import derive_readonly_capability

    handle = derive_readonly_capability("explorer")

    assert handle.actions == {CapabilityAction.READ}
    assert handle.scope.paths == ()
    assert handle.subject_id == "explorer"


def test_a_readonly_child_cannot_hand_write_access_to_its_own_child(workspace: Path) -> None:
    parent = SimpleNamespace(_last_context={"workspace_path": str(workspace)})

    with capability_scope(_handle(workspace, readonly=True)):
        assert coerce_spawn_readonly(parent, False) is True
        with pytest.raises(AttenuationError, match="Action elevation denied"):
            derive_spawn_capability(parent_agent=parent, agent_type="grandchild", readonly=False)
