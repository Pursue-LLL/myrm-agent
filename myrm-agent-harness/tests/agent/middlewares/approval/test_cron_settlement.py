"""A scheduled run has nobody to answer an approval ask, so none of its calls waits for one.

Verifies, through the real approval middleware:
1. A cron job's security config carries the mark; a run is a scheduled one by that mark or by its session key.
2. No call of a scheduled run waits for a person: not the job's own agent, nor an agent or workflow node it
   delegated to (their session key is not a cron key), not under YOLO, not when the reviewer cannot settle the call.
3. The job's declared capabilities answer in place of the person, YOLO or not: a declared call runs, an undeclared
   one is refused; the calls ``_cron_policy.cron_never_class`` names (payment-like calls, integration writes, egress
   after a credential read, paths the path policy does not allow) are refused either way.
4. A run nobody scheduled keeps waiting for its person about what YOLO does not wave through, and YOLO still
   approves the rest for the person who switched it on.
5. A delegated agent of a scheduled job is told in the unattended wording once its refusals pile up.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from langchain_core.messages import ToolCall

from myrm_agent_harness.agent.middlewares.approval import set_security_config
from myrm_agent_harness.agent.middlewares.approval._cron_policy import is_cron_run
from myrm_agent_harness.agent.middlewares.approval.batch_processor import (
    evaluate_tool_batch,
    register_security_reviewer,
)
from myrm_agent_harness.agent.middlewares.approval.helpers import record_denial
from myrm_agent_harness.agent.security.audit import get_audit_entries
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.types import ReviewDecision

from .cron_run_support import (
    DELEGATED_AGENT,
    JOB_AGENT,
    NEVER_CLASSES,
    RUNS,
    YOLO_OR_NOT,
    Dirs,
    FixedReviewer,
    allow_always,
    cron_config,
    isolated_run,
    outcome,
)

# Run when the job declared the capability, refused when it did not.
_BY_DECLARATION = ("pip-install", "git-push", "delete-build-dir", "write-note")


@pytest.fixture(autouse=True)
def _isolation(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    yield from isolated_run(monkeypatch)


@pytest.fixture
def dirs(tmp_path_factory: pytest.TempPathFactory) -> Dirs:
    return Dirs(
        workspace=tmp_path_factory.mktemp("cronws"),
        elsewhere=tmp_path_factory.mktemp("elsewhere"),
    )


class TestTheRunIsScheduled:
    def test_only_a_cron_config_carries_the_mark(self) -> None:
        assert build_channel_security_config("cron").is_cron
        assert not build_channel_security_config("web_chat").is_cron
        assert not build_channel_security_config("im").is_cron

    def test_the_mark_makes_any_session_a_scheduled_run(self) -> None:
        assert is_cron_run(build_channel_security_config("cron"), DELEGATED_AGENT)

    def test_a_cron_session_key_alone_makes_a_scheduled_run(self) -> None:
        assert is_cron_run(None, JOB_AGENT)
        assert is_cron_run(build_channel_security_config("web_chat"), JOB_AGENT)

    def test_neither_mark_nor_key_is_a_run_somebody_attends(self) -> None:
        assert not is_cron_run(None, "chat:1")
        assert not is_cron_run(build_channel_security_config("web_chat"), "chat:1")


class TestNothingWaits:
    @RUNS
    @YOLO_OR_NOT
    async def test_no_call_waits_for_a_person(self, session: str, yolo: bool, dirs: Dirs) -> None:
        waiting = [
            f"{name} (declared={declared})"
            for declared in (True, False)
            for name, call in dirs.calls().items()
            if await outcome(session, cron_config(yolo=yolo, declared=declared), call, dirs) == "waiting"
        ]

        assert waiting == []

    @RUNS
    async def test_the_batch_never_leaves_a_pending_call(self, session: str, dirs: Dirs) -> None:
        calls = [
            ToolCall(type="tool_call", name=call.tool, args=call.args, id=name) for name, call in dirs.calls().items()
        ]
        for config in (cron_config(), cron_config(declared=False), cron_config(yolo=True)):
            _approved, _denied, pending = await evaluate_tool_batch(
                calls,
                config,
                is_cron=True,
                workspace_root=str(dirs.workspace),
                session_key=session,
                args_hashes={},
                is_interactive=False,
            )

            assert pending == []


class TestDeclarationsAnswerInPlaceOfThePerson:
    @RUNS
    @YOLO_OR_NOT
    @pytest.mark.parametrize("name", _BY_DECLARATION)
    async def test_a_declared_call_runs_and_an_undeclared_one_is_refused(
        self, session: str, yolo: bool, name: str, dirs: Dirs
    ) -> None:
        call = dirs.calls()[name]

        assert await outcome(session, cron_config(yolo=yolo, declared=True), call, dirs) == "approved"
        assert await outcome(session, cron_config(yolo=yolo, declared=False), call, dirs) == "refused"

    @RUNS
    @YOLO_OR_NOT
    @pytest.mark.parametrize("name", NEVER_CLASSES)
    async def test_the_declaration_never_covers_these(self, session: str, yolo: bool, name: str, dirs: Dirs) -> None:
        call = dirs.calls()[name]

        assert await outcome(session, cron_config(yolo=yolo, declared=True), call, dirs) == "refused"
        assert await outcome(session, cron_config(yolo=yolo, declared=False), call, dirs) == "refused"

    @RUNS
    async def test_settled_calls_leave_an_audit_trail(self, session: str, dirs: Dirs) -> None:
        calls = dirs.calls()
        await outcome(session, cron_config(declared=True), calls["pip-install"], dirs)
        await outcome(session, cron_config(declared=False), calls["pip-install"], dirs)

        decisions = [e.decision for e in get_audit_entries() if e.tool_name == "bash_code_execute_tool"]

        assert decisions == ["ALLOW", "CRON_DENY"]


class TestReviewerThatCannotSettleTheCall:
    @RUNS
    async def test_an_uncertain_reviewer_leaves_the_declaration_to_answer(self, session: str, dirs: Dirs) -> None:
        call = dirs.calls()["pip-install"]
        await allow_always(call, command_pattern="pip install *")
        register_security_reviewer(FixedReviewer(ReviewDecision.UNCERTAIN))

        assert await outcome(session, cron_config(declared=True), call, dirs) == "approved"
        assert await outcome(session, cron_config(declared=False), call, dirs) == "refused"

    @RUNS
    async def test_a_refusing_reviewer_refuses_the_call(self, session: str, dirs: Dirs) -> None:
        call = dirs.calls()["pip-install"]
        await allow_always(call, command_pattern="pip install *")
        register_security_reviewer(FixedReviewer(ReviewDecision.DENY))

        assert await outcome(session, cron_config(declared=True), call, dirs) == "refused"


class TestRunsNobodyScheduledKeepWaiting:
    @pytest.mark.parametrize("name", ["git-push", "delete-build-dir"])
    async def test_yolo_still_asks_a_person_about_what_it_does_not_wave_through(self, name: str, dirs: Dirs) -> None:
        config = build_channel_security_config("web_chat", {"yoloModeEnabled": True})

        assert await outcome("chat:1", config, dirs.calls()[name], dirs) == "waiting"

    async def test_an_ordinary_ask_waits_for_the_person(self, dirs: Dirs) -> None:
        config = build_channel_security_config("web_chat")

        assert await outcome("chat:1", config, dirs.calls()["pip-install"], dirs) == "waiting"

    @pytest.mark.parametrize("name", ["pip-install", "write-outside-zone", "egress-after-credential-read"])
    async def test_yolo_approves_the_asks_the_person_who_switched_it_on_would_answer(
        self, name: str, dirs: Dirs
    ) -> None:
        config = build_channel_security_config("web_chat", {"yoloModeEnabled": True})

        assert await outcome("chat:1", config, dirs.calls()[name], dirs) == "approved"


class TestRefusalWordingInADelegatedAgent:
    def test_piled_up_refusals_get_the_unattended_note(self) -> None:
        set_security_config(cron_config())

        notes = [record_denial("bash_code_execute_tool", DELEGATED_AGENT) for _ in range(3)]

        assert "scheduled job" in notes[-1]
        assert "auto-mode" not in notes[-1].lower()

    def test_a_run_somebody_attends_gets_the_attended_note(self) -> None:
        set_security_config(build_channel_security_config("web_chat"))

        notes = [record_denial("bash_code_execute_tool", "chat:1") for _ in range(3)]

        assert "scheduled job" not in notes[-1]
