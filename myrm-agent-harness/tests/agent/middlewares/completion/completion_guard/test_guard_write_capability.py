"""The completion guard demands a saved file only from a run that can save one.

A run can save a file when ``file_write_tool`` is mounted and the security policy does not deny
``file_write``. Without either, the demand "call file_write_tool" can never be met: the model repeats its answer
for every rejection (one paid model call each) and the forced finish then writes the draft into the workspace
itself, past the policy. Guard-level cases pin the decision, the built-chain cases pin that ``build_middlewares``
wires the capability from the mounted tools and the policy, and the ``create_skill_agent`` cases run the real tool
assembly and run loop with only the model scripted.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from langchain_core.messages import AIMessage

from myrm_agent_harness.agent.meta_tools.mount_policy import FileAccessMode
from myrm_agent_harness.agent.middlewares._session_context import set_security_config
from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    CompletionGuard,
    reset_completion_guard,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.capabilities import CompletionCapabilities
from myrm_agent_harness.agent.middlewares.completion.completion_guard.directive import BlockReasons
from tests.support.completion_guard_harness import (
    CountingModel,
    built_guard,
    named_tool,
    reasons_of,
    registry_of,
    run_agent,
    runtime,
    state,
    tool_names,
    verdict,
    writes_allowed,
    writes_denied,
)

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


def _saving(allowed: bool, *, max_rejections: int = 3) -> CompletionGuard:
    capabilities = CompletionCapabilities(can_save_files=lambda runtime: allowed)
    return CompletionGuard(max_rejections=max_rejections, capabilities=capabilities)


def _asked(reply: str = _REPLY, request: str = _REQUEST) -> dict[str, object]:
    return state(request, reply)


class TestGuardDecision:
    def setup_method(self) -> None:
        reset_completion_guard()

    @pytest.mark.asyncio
    async def test_a_run_that_can_save_files_is_asked_to_save_the_file(self, tmp_path: Path) -> None:
        result = await verdict(_saving(True), _asked(), runtime(tmp_path))

        assert "Substantial unpersisted deliverables" in reasons_of(result).deliverable_write

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_save_files_is_not_asked(self, tmp_path: Path) -> None:
        assert await verdict(_saving(False), _asked(), runtime(tmp_path)) is None

    @pytest.mark.asyncio
    async def test_the_run_is_asked_per_call_with_the_runtime_of_that_call(self, tmp_path: Path) -> None:
        seen: list[object] = []
        saves = {"allowed": False}

        def can_save_files(runtime: object) -> bool:
            seen.append(runtime)
            return saves["allowed"]

        guard = CompletionGuard(capabilities=CompletionCapabilities(can_save_files=can_save_files))
        first, second = runtime(tmp_path), runtime(tmp_path)

        assert await verdict(guard, _asked(), first) is None
        saves["allowed"] = True
        assert await verdict(guard, _asked(), second) is not None
        assert seen == [first, second]

    @pytest.mark.asyncio
    async def test_a_false_saved_claim_is_still_blocked_for_a_run_that_cannot_save_files(self, tmp_path: Path) -> None:
        messages = _asked("Saved to `out/report.md`", "write the report")

        result = await verdict(_saving(False), messages, runtime(tmp_path))

        assert "no successful file_write_tool" in reasons_of(result).deliverable_write


class TestForcedFinishStaging:
    """Staging writes the draft into the workspace; only a run that can save files gets one."""

    def setup_method(self) -> None:
        reset_completion_guard()

    async def _forced_finish_reasons(self, guard: CompletionGuard, tmp_path: Path) -> BlockReasons:
        messages = _asked(_REPLY_WITH_UNBACKED_CLAIM)
        first = await verdict(guard, messages, runtime(tmp_path))
        assert first is not None
        reasons = reasons_of(await verdict(guard, messages, runtime(tmp_path)))
        assert reasons.forced_finish is True
        return reasons

    @pytest.mark.asyncio
    async def test_a_run_that_can_save_files_stages_the_draft(self, tmp_path: Path) -> None:
        reasons = await self._forced_finish_reasons(_saving(True, max_rejections=1), tmp_path)

        assert len(reasons.staged_artifacts) == 1
        assert len(list((tmp_path / _STAGED_DIR).glob("*_draft_worker.py"))) == 1

    @pytest.mark.asyncio
    async def test_a_run_that_cannot_save_files_stages_nothing(self, tmp_path: Path) -> None:
        reasons = await self._forced_finish_reasons(_saving(False, max_rejections=1), tmp_path)

        assert reasons.staged_artifacts == ()
        assert not (tmp_path / ".myrm").exists()


class TestBuiltChainWiring:
    """``build_middlewares`` wires the capability from the mounted tools and the policy of the call."""

    def setup_method(self) -> None:
        reset_completion_guard()
        set_security_config(None)

    def teardown_method(self) -> None:
        set_security_config(None)

    @pytest.mark.asyncio
    async def test_a_run_without_the_write_tool_is_not_asked_even_where_the_policy_allows_it(
        self, tmp_path: Path
    ) -> None:
        guard = built_guard(registry_of([]))

        assert await verdict(guard, _asked(), runtime(tmp_path, writes_allowed(tmp_path))) is None

    @pytest.mark.asyncio
    async def test_a_run_with_the_write_tool_under_a_policy_that_allows_it_is_asked(self, tmp_path: Path) -> None:
        guard = built_guard(registry_of([named_tool("file_write_tool")]))

        assert await verdict(guard, _asked(), runtime(tmp_path, writes_allowed(tmp_path))) is not None

    @pytest.mark.asyncio
    async def test_a_policy_that_denies_file_write_is_not_asked_even_with_the_write_tool(self, tmp_path: Path) -> None:
        guard = built_guard(registry_of([named_tool("file_write_tool")]))

        assert await verdict(guard, _asked(), runtime(tmp_path, writes_denied(tmp_path))) is None


class TestRealAgent:
    """Whole agent: tool assembly, middleware chain and run loop are real; only the model is scripted."""

    @staticmethod
    def _model() -> CountingModel:
        return CountingModel(responses=[AIMessage(content=_REPLY) for _ in range(8)])

    @pytest.mark.asyncio
    async def test_a_run_mounted_without_the_write_tool_answers_once_and_writes_nothing(self, tmp_path: Path) -> None:
        model = self._model()

        agent, workspace = await run_agent(
            tmp_path,
            writes_allowed(tmp_path),
            model,
            request=_REQUEST,
            file_access_mode=FileAccessMode.SPILL_AND_UPLOADS,
            enable_shell_tools=False,
        )

        assert "file_write_tool" not in tool_names(agent)
        assert len(model.requests) == 1
        assert not (workspace / ".myrm").exists()

    @pytest.mark.asyncio
    async def test_a_run_whose_policy_denies_writes_answers_once_and_writes_nothing(self, tmp_path: Path) -> None:
        model = self._model()

        agent, workspace = await run_agent(
            tmp_path,
            writes_denied(tmp_path),
            model,
            request=_REQUEST,
            file_access_mode=FileAccessMode.FULL,
            enable_shell_tools=True,
        )

        assert "file_write_tool" in tool_names(agent)
        assert len(model.requests) == 1
        assert not (workspace / ".myrm").exists()

    @pytest.mark.asyncio
    async def test_a_run_that_may_write_is_still_pressed_to_save_the_file(self, tmp_path: Path) -> None:
        model = self._model()

        agent, workspace = await run_agent(
            tmp_path,
            writes_allowed(tmp_path),
            model,
            request=_REQUEST,
            file_access_mode=FileAccessMode.FULL,
            enable_shell_tools=True,
        )

        assert "file_write_tool" in tool_names(agent)
        assert len(model.requests) > 1
        assert len(list((workspace / _STAGED_DIR).glob("*_draft_worker.py"))) == 1
