"""The completion guard demands a saved file only from a run that can save one.

A run can save a file when ``file_write_tool`` is mounted and the security policy does not deny
``file_write``. Without either, the demand "call file_write_tool" can never be met: the model repeats its answer
for every rejection (one paid model call each) and the forced finish then writes the draft into the workspace
itself, past the policy. Guard-level cases pin the decision, the built-chain cases pin what the probe wired by
``build_middlewares`` reads, and the ``create_skill_agent`` cases run the real tool assembly and run loop with only
the model scripted.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage
from langchain_core.tools import tool
from langgraph.runtime import Runtime
from pydantic import Field

from myrm_agent_harness.agent._factory.builder import create_skill_agent
from myrm_agent_harness.agent._internals._agent_build import build_middlewares
from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares._session_context import (
    EFFECTIVE_SECURITY_CONFIG_CONTEXT_KEY,
    set_security_config,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    COMPLETION_CHECK_TOOL_NAME,
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.skill_agent import SkillAgent
from myrm_agent_harness.agent.tool_management import ToolRegistry, ToolSource
from myrm_agent_harness.agent.types import WorkspaceBinding
from myrm_agent_harness.api import AgentRuntimeSpec
from myrm_agent_harness.core.security.types import PermissionAction, PermissionRule, SecurityConfig
from myrm_agent_harness.toolkits.storage.local import LocalStorageBackend

LOOP_GUARD_PATCH = "myrm_agent_harness.agent.middlewares.tooling.tool_interceptor_middleware.get_loop_guard"

_CODE = (
    "```python\n"
    "# filename: draft_worker.py\n"
    "import time\n"
    "\n"
    "def run_worker():\n"
    "    print('working')\n"
    "    time.sleep(1)\n"
    "```"
)
_REQUEST = "写一个 worker 脚本"
# A test run the trace cannot back: a critical error every run is held to, whether or not it can save files.
_REPLY_WITH_UNBACKED_CLAIM = f"我已经运行了测试，全部通过。\n{_CODE}"
_REPLY = f"完成：\n{_CODE}"
_STAGED_DIR = Path(".myrm") / "staged_artifacts"

_READ_ONLY_DENIALS = tuple(
    PermissionRule(permission, "*", PermissionAction.DENY)
    for permission in ("file_write", "file_edit", "file_delete", "shell_exec", "code_interpreter")
)


def _state(request: str = _REQUEST, reply: str = _REPLY) -> dict[str, object]:
    return {"messages": [HumanMessage(content=request), AIMessage(content=reply)]}


def _runtime(workspace: Path, security: SecurityConfig | None = None) -> Runtime:  # type: ignore[type-arg]
    context: dict[str, object] = {"workspace_path": str(workspace)}
    if security is not None:
        context[EFFECTIVE_SECURITY_CONFIG_CONTEXT_KEY] = security
    return Runtime(context=context)


async def _verdict(guard: CompletionGuard, state: dict[str, object], runtime: Runtime) -> dict[str, object] | None:  # type: ignore[type-arg]
    with patch(LOOP_GUARD_PATCH) as loop_guard:
        loop_guard.return_value._window = []
        return await guard.aafter_model(state, runtime)


def _writes_allowed(workspace: Path) -> SecurityConfig:
    base = SecurityConfig.workspace(allowed_roots=(str(workspace),))
    return replace(base, ruleset=(*base.ruleset, PermissionRule("*", "*", PermissionAction.ALLOW)))


def _writes_denied(workspace: Path) -> SecurityConfig:
    """The deny set of the server's built-in Read Only profile on top of an otherwise permissive policy."""
    allowed = _writes_allowed(workspace)
    return replace(allowed, ruleset=(*allowed.ruleset, *_READ_ONLY_DENIALS))


class TestGuardDecision:
    def setup_method(self) -> None:
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_a_run_that_can_save_files_is_asked_to_save_the_file(self, tmp_path: Path) -> None:
        guard = CompletionGuard(can_save_files=lambda runtime: True)

        result = await _verdict(guard, _state(), _runtime(tmp_path))

        assert result is not None
        call = result["messages"][0].tool_calls[0]
        assert call["name"] == COMPLETION_CHECK_TOOL_NAME
        assert "Substantial unpersisted deliverables" in call["args"]["deliverable_write_reason"]

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_save_files_is_not_asked(self, tmp_path: Path) -> None:
        guard = CompletionGuard(can_save_files=lambda runtime: False)

        assert await _verdict(guard, _state(), _runtime(tmp_path)) is None

    @pytest.mark.asyncio
    async def test_the_run_is_asked_per_call_with_the_runtime_of_that_call(self, tmp_path: Path) -> None:
        seen: list[object] = []
        saves = {"allowed": False}

        def can_save_files(runtime: object) -> bool:
            seen.append(runtime)
            return saves["allowed"]

        guard = CompletionGuard(can_save_files=can_save_files)
        first, second = _runtime(tmp_path), _runtime(tmp_path)

        assert await _verdict(guard, _state(), first) is None
        saves["allowed"] = True
        assert await _verdict(guard, _state(), second) is not None
        assert seen == [first, second]

    @pytest.mark.asyncio
    async def test_a_false_saved_claim_is_still_blocked_for_a_run_that_cannot_save_files(self, tmp_path: Path) -> None:
        guard = CompletionGuard(can_save_files=lambda runtime: False)
        state = _state(request="write the report", reply="Saved to `out/report.md`")

        result = await _verdict(guard, state, _runtime(tmp_path))

        assert result is not None
        assert (
            "no successful file_write_tool" in result["messages"][0].tool_calls[0]["args"]["deliverable_write_reason"]
        )


class TestForcedFinishStaging:
    """Staging writes the draft into the workspace; only a run that can save files gets one."""

    def setup_method(self) -> None:
        reset_completion_guard()

    async def _forced_finish_args(self, guard: CompletionGuard, runtime: Runtime) -> dict[str, object]:  # type: ignore[type-arg]
        state = _state(reply=_REPLY_WITH_UNBACKED_CLAIM)
        first = await _verdict(guard, state, runtime)
        assert first is not None
        forced = await _verdict(guard, state, runtime)
        assert forced is not None
        args = forced["messages"][0].tool_calls[0]["args"]
        assert args["force_fail"] is True
        return args

    @pytest.mark.asyncio
    async def test_a_run_that_can_save_files_stages_the_draft(self, tmp_path: Path) -> None:
        guard = CompletionGuard(max_rejections=1, can_save_files=lambda runtime: True)

        args = await self._forced_finish_args(guard, _runtime(tmp_path))

        assert len(args["staged_artifacts"]) == 1
        assert len(list((tmp_path / _STAGED_DIR).glob("*_draft_worker.py"))) == 1

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_save_files_stages_nothing(self, tmp_path: Path) -> None:
        guard = CompletionGuard(max_rejections=1, can_save_files=lambda runtime: False)

        args = await self._forced_finish_args(guard, _runtime(tmp_path))

        assert "staged_artifacts" not in args
        assert not (tmp_path / ".myrm").exists()


@tool
def file_write_tool(path: str, content: str) -> str:
    """Write a file."""
    return f"wrote {path}"


def _built_guard(*, mounts_write_tool: bool) -> CompletionGuard:
    """The CompletionGuard of the chain ``build_middlewares`` assembles over a registry."""
    registry = ToolRegistry()
    if mounts_write_tool:
        registry.register(file_write_tool, source=ToolSource.META)
    for middleware in build_middlewares(registry, []):
        # The chain may hand a middleware over inside a sync-parity wrapper that keeps it as ``_inner``.
        inner = vars(middleware).get("_inner", middleware)
        if isinstance(inner, CompletionGuard):
            return inner
    raise AssertionError("no CompletionGuard in the chain")


class TestBuiltChainProbe:
    """What the probe ``build_middlewares`` hands the guard reads: the mounted tools and the policy."""

    def setup_method(self) -> None:
        reset_completion_guard()
        set_security_config(None)

    def teardown_method(self) -> None:
        set_security_config(None)

    @pytest.mark.asyncio
    async def test_a_run_without_the_write_tool_is_not_asked_even_where_the_policy_allows_it(
        self, tmp_path: Path
    ) -> None:
        guard = _built_guard(mounts_write_tool=False)

        assert await _verdict(guard, _state(), _runtime(tmp_path, _writes_allowed(tmp_path))) is None

    @pytest.mark.asyncio
    async def test_a_run_with_the_write_tool_under_a_policy_that_allows_it_is_asked(self, tmp_path: Path) -> None:
        guard = _built_guard(mounts_write_tool=True)

        assert await _verdict(guard, _state(), _runtime(tmp_path, _writes_allowed(tmp_path))) is not None

    @pytest.mark.asyncio
    async def test_a_run_with_the_write_tool_and_no_known_policy_is_asked(self, tmp_path: Path) -> None:
        guard = _built_guard(mounts_write_tool=True)

        assert await _verdict(guard, _state(), _runtime(tmp_path)) is not None

    @pytest.mark.asyncio
    async def test_a_policy_that_denies_file_write_is_not_asked_even_with_the_write_tool(self, tmp_path: Path) -> None:
        guard = _built_guard(mounts_write_tool=True)

        assert await _verdict(guard, _state(), _runtime(tmp_path, SecurityConfig.readonly())) is None
        assert await _verdict(guard, _state(), _runtime(tmp_path, _writes_denied(tmp_path))) is None

    @pytest.mark.asyncio
    async def test_the_policy_bound_to_the_run_is_read_when_the_turn_snapshot_is_absent(self, tmp_path: Path) -> None:
        guard = _built_guard(mounts_write_tool=True)
        set_security_config(SecurityConfig.readonly())

        assert await _verdict(guard, _state(), _runtime(tmp_path)) is None

    @pytest.mark.asyncio
    async def test_the_turn_snapshot_wins_over_the_policy_bound_to_the_run(self, tmp_path: Path) -> None:
        guard = _built_guard(mounts_write_tool=True)
        set_security_config(SecurityConfig.readonly())

        assert await _verdict(guard, _state(), _runtime(tmp_path, _writes_allowed(tmp_path))) is not None


class _CountingModel(FakeMessagesListChatModel):
    """Repeats one scripted answer and counts the model calls it serves."""

    requests: list[int] = Field(default_factory=list)

    def bind_tools(self, tools: object, **kwargs: object) -> _CountingModel:
        return self

    def _generate(self, messages: list[BaseMessage], *args: object, **kwargs: object):  # type: ignore[no-untyped-def]
        self.requests.append(len(messages))
        return super()._generate(messages, *args, **kwargs)


async def _run(
    tmp_path: Path,
    security: SecurityConfig,
    *,
    file_access_mode: FileAccessMode,
    enable_shell_tools: bool,
) -> tuple[_CountingModel, SkillAgent, Path]:
    workspace = (tmp_path / "project").resolve()
    workspace.mkdir()
    model = _CountingModel(responses=[AIMessage(content=_REPLY) for _ in range(8)])
    chat = "chat_write_capability"
    agent = await create_skill_agent(
        spec=AgentRuntimeSpec(
            agent_id="writer",
            name="writer",
            system_prompt="You answer coding requests.",
            skill_ids=[],
            workspace_binding=WorkspaceBinding(mode="chat", root_path=str(workspace), chat_id=chat),
            security_config=security,
        ),
        llm=model,
        tools=[],
        storage_backend=LocalStorageBackend(str(tmp_path / "storage")),
        checkpointer=False,
        file_access_mode=file_access_mode,
        enable_shell_tools=enable_shell_tools,
    )
    context: dict[str, object] = {
        "workspace_path": str(workspace),
        "workspace_binding": WorkspaceBinding(mode="chat", root_path=str(workspace), chat_id=chat),
        "workspaces_storage_root": str(tmp_path / "workspaces"),
        "session_id": chat,
    }
    async for _ in agent.run(query=_REQUEST, context=context):
        pass
    return model, agent, workspace


def _tool_names(agent: SkillAgent) -> set[str]:
    assert agent._cached_tools is not None
    return {tool.name for tool in agent._cached_tools}


class TestRealAgent:
    """Whole agent: tool assembly, middleware chain and run loop are real; only the model is scripted."""

    @pytest.mark.asyncio
    async def test_a_run_mounted_without_the_write_tool_answers_once_and_writes_nothing(self, tmp_path: Path) -> None:
        security = _writes_allowed(tmp_path)

        model, agent, workspace = await _run(
            tmp_path, security, file_access_mode=FileAccessMode.SPILL_AND_UPLOADS, enable_shell_tools=False
        )

        assert "file_write_tool" not in _tool_names(agent)
        assert len(model.requests) == 1
        assert not (workspace / ".myrm").exists()

    @pytest.mark.asyncio
    async def test_a_run_whose_policy_denies_writes_answers_once_and_writes_nothing(self, tmp_path: Path) -> None:
        security = _writes_denied(tmp_path)

        model, agent, workspace = await _run(
            tmp_path, security, file_access_mode=FileAccessMode.FULL, enable_shell_tools=True
        )

        assert "file_write_tool" in _tool_names(agent)
        assert len(model.requests) == 1
        assert not (workspace / ".myrm").exists()

    @pytest.mark.asyncio
    async def test_a_run_that_may_write_is_still_pressed_to_save_the_file(self, tmp_path: Path) -> None:
        security = _writes_allowed(tmp_path)

        model, agent, workspace = await _run(
            tmp_path, security, file_access_mode=FileAccessMode.FULL, enable_shell_tools=True
        )

        assert "file_write_tool" in _tool_names(agent)
        assert len(model.requests) > 1
        assert len(list((workspace / _STAGED_DIR).glob("*_draft_worker.py"))) == 1
