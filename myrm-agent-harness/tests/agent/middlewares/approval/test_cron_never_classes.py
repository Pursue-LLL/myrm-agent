"""What no job's declaration can approve stays refused, whoever else approved the call.

A scheduled run has nobody to ask, so the job's declared capabilities, a standing approval of the user and the
automatic reviewer answer in place of the person. Payment-like calls, integration writes, writes to protected
instruction files (through a file tool or a shell command), data leaving the session after a credential read and paths
outside the run's zones are outside all three. Verifies, through the real approval middleware:
1. Those calls are refused in every session of a run and whatever approved them, declared job or not.
2. YOLO does not judge a scheduled run: every call gets the same outcome with it on or off.
3. A standing approval still answers an ordinary ask, and a run somebody attends is untouched.
4. Refusals piling up never suspend a scheduled run: a call the engine allows keeps running.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.middlewares.approval._cron_policy import CronAskVerdict, cron_never_class
from myrm_agent_harness.agent.middlewares.approval.batch_processor import (
    evaluate_tool_batch,
    register_security_reviewer,
)
from myrm_agent_harness.agent.middlewares.approval.helpers import clear_all_session_denials_for_tests, record_denial
from myrm_agent_harness.agent.security.audit import get_audit_entries
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.guards.taint_tracker import get_taint_tracker
from myrm_agent_harness.agent.security.tool_registry import resolve_permission_type
from myrm_agent_harness.agent.security.types import ReviewDecision, SecurityConfig
from myrm_agent_harness.core.security.readonly_research_sandbox import get_readonly_research_sandbox_facade

from .cron_run_support import (
    JOB_AGENT,
    NEVER_CLASSES,
    RUNS,
    YOLO_OR_NOT,
    Call,
    Dirs,
    FixedReviewer,
    Outcome,
    allow_always,
    cron_config,
    isolated_run,
    outcome,
)

_ORDINARY = ("pip-install", "git-push", "write-note", "read-note")
_APPROVERS = pytest.mark.parametrize("approver", ["allow-always", "reviewer", "both"])


@pytest.fixture(autouse=True)
def _isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from isolated_run(monkeypatch)


@pytest.fixture
def dirs(tmp_path_factory: pytest.TempPathFactory) -> Dirs:
    return Dirs(
        workspace=tmp_path_factory.mktemp("cronws"),
        elsewhere=tmp_path_factory.mktemp("elsewhere"),
    )


async def _approve_beforehand(approver: str, call: Call) -> None:
    """Have the user's standing approval, the automatic reviewer or both approve *call*."""
    if approver != "reviewer":
        await allow_always(call)
    if approver != "allow-always":
        register_security_reviewer(FixedReviewer(ReviewDecision.ALLOW))


async def _fresh_outcome(session: str, config: SecurityConfig, call: Call, dirs: Dirs) -> Outcome:
    """The outcome of *call* with no refusal counted before it."""
    clear_all_session_denials_for_tests()
    return await outcome(session, config, call, dirs)


def _never_class(call: Call, config: SecurityConfig, dirs: Dirs) -> CronAskVerdict | None:
    if call.after_credential_read:
        get_taint_tracker().record_tool_output("file_read_tool", {"paths": [".env"]})
    return cron_never_class(
        permission_type=resolve_permission_type(call.tool, call.args),
        tool_name=call.tool,
        tool_input=call.args,
        config=config,
        workspace_root=str(dirs.workspace),
    )


class TestNothingOvercomesTheFloors:
    @RUNS
    @_APPROVERS
    @pytest.mark.parametrize("name", NEVER_CLASSES)
    async def test_the_call_is_refused_whoever_approved_it(
        self, session: str, approver: str, name: str, dirs: Dirs
    ) -> None:
        call = dirs.calls()[name]
        await _approve_beforehand(approver, call)

        for declared in (True, False):
            assert await _fresh_outcome(session, cron_config(declared=declared), call, dirs) == "refused"

    async def test_an_overridden_approval_comes_back_as_a_refusal_with_an_audit_row(self, dirs: Dirs) -> None:
        call = dirs.calls()["write-outside-zone"]
        await allow_always(call)
        tool_call = ToolCall(type="tool_call", name=call.tool, args=call.args, id="call_1")

        approved, denied, pending = await evaluate_tool_batch(
            [tool_call],
            cron_config(),
            is_cron=True,
            workspace_root=str(dirs.workspace),
            session_key=JOB_AGENT,
            args_hashes={},
            is_interactive=False,
        )

        assert (approved, pending) == ([], [])
        assert [index for index, _call, _text in denied] == [0]
        assert "A cron job cannot ask for approval" in denied[0][2]
        assert [e.decision for e in get_audit_entries() if e.tool_name == call.tool][-1] == "CRON_DENY"


class TestCronNeverClass:
    @pytest.mark.parametrize("name", NEVER_CLASSES)
    def test_names_the_class_whatever_the_job_declared(self, name: str, dirs: Dirs) -> None:
        for declared in (True, False):
            verdict = _never_class(dirs.calls()[name], cron_config(declared=declared), dirs)

            assert verdict is not None
            assert verdict.denied

    @pytest.mark.parametrize("name", _ORDINARY)
    def test_leaves_every_other_call_to_the_declaration(self, name: str, dirs: Dirs) -> None:
        for declared in (True, False):
            assert _never_class(dirs.calls()[name], cron_config(declared=declared), dirs) is None


class TestYoloDoesNotJudgeAScheduledRun:
    @RUNS
    @pytest.mark.parametrize("approver", ["none", "allow-always", "reviewer", "both"])
    async def test_every_call_gets_the_same_outcome_with_yolo_on_or_off(
        self, session: str, approver: str, dirs: Dirs
    ) -> None:
        differing: list[str] = []
        for name, call in dirs.calls().items():
            if approver != "none":
                await _approve_beforehand(approver, call)
            for declared in (True, False):
                plain = await _fresh_outcome(session, cron_config(declared=declared), call, dirs)
                yolo = await _fresh_outcome(session, cron_config(yolo=True, declared=declared), call, dirs)
                if plain != yolo:
                    differing.append(f"{name} (declared={declared}): plain {plain}, yolo {yolo}")

        assert differing == []


class TestOrdinaryAsksAreStillAnswered:
    @RUNS
    @YOLO_OR_NOT
    async def test_a_standing_approval_answers_an_ordinary_ask(self, session: str, yolo: bool, dirs: Dirs) -> None:
        call = dirs.calls()["pip-install"]
        await allow_always(call)

        assert await outcome(session, cron_config(yolo=yolo, declared=False), call, dirs) == "approved"


class TestRefusalsDoNotSuspendARunNobodyAnswers:
    @RUNS
    @YOLO_OR_NOT
    async def test_a_call_the_engine_allows_keeps_running_after_refusals_pile_up(
        self, session: str, yolo: bool, dirs: Dirs
    ) -> None:
        read = dirs.calls()["read-note"]
        for _ in range(3):
            record_denial("bash_code_execute_tool", session)

        assert await outcome(session, cron_config(yolo=yolo, declared=False), read, dirs) == "approved"

    async def test_a_leased_research_job_keeps_its_read_tools_after_its_shell_calls_were_refused(
        self, dirs: Dirs
    ) -> None:
        facade = get_readonly_research_sandbox_facade()
        facade.grant_research_lease(JOB_AGENT)
        config = cron_config(declared=False)
        try:
            for _ in range(3):
                assert await outcome(JOB_AGENT, config, dirs.calls()["pip-install"], dirs) == "refused"

            assert await outcome(JOB_AGENT, config, dirs.calls()["read-note"], dirs) == "approved"
        finally:
            facade.revoke_lease(JOB_AGENT)

    async def test_a_run_somebody_attends_is_still_suspended(self, dirs: Dirs) -> None:
        for _ in range(3):
            record_denial("bash_code_execute_tool", "chat:1")

        config = build_channel_security_config("web_chat")

        assert await outcome("chat:1", config, dirs.calls()["read-note"], dirs) == "waiting"
