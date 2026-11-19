"""A write that only a person may answer is released by no automatic approver.

The engine asks for a write to a protected instruction file, and for a write to a repository's git hooks or config,
under a stable code, and no standing approval (rule, allowlist entry, scheduled job) lifts either ask. Three approvers
act without a person: YOLO mode, auto mode's security reviewer, and an approval expiry set to allow. Each must treat
these asks the way it treats a payment. Verifies, with the real engine, the real decision stages and the real
interrupt payload:
1. YOLO holds such a write for a person, on the card shown without YOLO, and still releases the other asks it always
   released.
2. Auto mode's reviewer is not asked about such a write, and is still asked about the other asks.
3. An expiry set to allow becomes deny for a batch that holds such a write, a socially irreversible call or an
   irreversible destructive call; a payment (its digest already refuses an answer the timer sends), an ordinary ask
   and an expiry that was set to deny are unchanged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolCall

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval._interrupt_payload import build_interrupt_payload
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode, CodedReason
from myrm_agent_harness.agent.security.audit import get_audit_entries, reset_audit_log
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.types import PathPolicy, ReviewDecision, ReviewResult, SecurityConfig
from myrm_agent_harness.agent.security.workspace_trust.context import clear_workspace_trust_context

_REVIEWER = "myrm_agent_harness.agent.middlewares.approval._batch_review._security_reviewer"
_NO_ZONES = PathPolicy(forbidden_paths=frozenset(), access_roots=())
_DEFAULT = SecurityConfig(path_policy=_NO_ZONES)
_YOLO = SecurityConfig(path_policy=_NO_ZONES, yolo_mode_enabled=True)

Batch = tuple[
    list[tuple[int, ToolCall]],
    list[tuple[int, ToolCall, str]],
    list[tuple[int, ToolCall, str, str, dict[str, object] | None]],
]


def _file_write(path: Path) -> ToolCall:
    return ToolCall(type="tool_call", name="file_write_tool", args={"file_path": str(path), "content": "x"}, id="c1")


def _shell(command: str) -> ToolCall:
    return ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": command}, id="c1")


def _charge() -> ToolCall:
    args: dict[str, object] = {"amount": 2500, "currency": "USD", "recipient": "acct_winner"}
    return ToolCall(type="tool_call", name="stripe_create_charge", args=args, id="c1")


# Each write only a person may answer: its id, the call that makes it in a workspace, and the code the engine asks under.
_HUMAN_ONLY_CASES = (
    ("instruction-file", lambda ws: _file_write(ws / "AGENTS.md"), ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE),
    ("shell-write", lambda _ws: _shell("echo x > AGENTS.md"), ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE),
    ("git-hook", lambda ws: _file_write(ws / ".git" / "hooks" / "pre-commit"), ApprovalReasonCode.GIT_METADATA_WRITE),
    ("git-config", lambda ws: _file_write(ws / ".git" / "config"), ApprovalReasonCode.GIT_METADATA_WRITE),
)
_HUMAN_ONLY = pytest.mark.parametrize(
    ("make", "code"), [pytest.param(make, code, id=name) for name, make, code in _HUMAN_ONLY_CASES]
)
_HUMAN_ONLY_CALLS = pytest.mark.parametrize(
    "make", [pytest.param(make, id=name) for name, make, _code in _HUMAN_ONLY_CASES]
)
# Asks the automatic approvers have always settled themselves.
_OTHER_ASKS = pytest.mark.parametrize(
    "make",
    [
        pytest.param(lambda ws: _file_write(ws.parent / "outside" / "notes.txt"), id="outside-the-zones"),
        pytest.param(lambda ws: _file_write(ws / ".env"), id="sensitive-file"),
    ],
)


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_taint_tracker()
    reset_audit_log()
    approval_flow._allowlist = approval_flow.Allowlist()
    clear_workspace_trust_context()
    yield
    clear_workspace_trust_context()
    reset_taint_tracker()
    reset_audit_log()


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    (tmp_path / "ws" / ".git" / "hooks").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    return tmp_path / "ws"


async def _evaluate(config: SecurityConfig, calls: list[ToolCall], workspace: Path) -> Batch:
    return await evaluate_tool_batch(
        calls,
        config,
        is_cron=False,
        workspace_root=str(workspace),
        session_key="human-only",
        args_hashes={},
        is_interactive=True,
    )


def _allow_reviewer() -> AsyncMock:
    reviewer = AsyncMock()
    reviewer.review = AsyncMock(return_value=ReviewResult(decision=ReviewDecision.ALLOW, reason="the user asked"))
    return reviewer


class TestYoloHoldsTheWrite:
    @_HUMAN_ONLY
    async def test_the_write_waits_for_a_person_under_its_own_audit_label(
        self, workspace: Path, make: Callable[[Path], ToolCall], code: ApprovalReasonCode
    ) -> None:
        call = make(workspace)

        approved, denied, pending = await _evaluate(_YOLO, [call], workspace)

        assert (approved, denied) == ([], [])
        assert [item[1] for item in pending] == [call]
        _idx, _call, _permission, reason, extra_ctx = pending[0]
        assert isinstance(reason, CodedReason)
        assert reason.code == code
        assert extra_ctx is not None
        assert (extra_ctx["high_risk"], extra_ctx["hide_allow_always"]) == (True, True)
        decisions = [entry.decision for entry in get_audit_entries()]
        assert "YOLO_PROTECTED_WRITE_BLOCKED" in decisions
        assert "YOLO_AUTO_APPROVE" not in decisions

    @_HUMAN_ONLY
    async def test_the_card_is_the_one_shown_without_yolo(
        self, workspace: Path, make: Callable[[Path], ToolCall], code: ApprovalReasonCode
    ) -> None:
        call = make(workspace)
        with patch(_REVIEWER, None):
            _approved, _denied, held = await _evaluate(_YOLO, [call], workspace)
            _approved, _denied, asked = await _evaluate(_DEFAULT, [call], workspace)

        held_card, _ = build_interrupt_payload(held, "human-only")
        asked_card, _ = build_interrupt_payload(asked, "human-only")

        assert held_card["actionRequests"] == asked_card["actionRequests"]
        assert held_card["actionRequests"][0]["reasonCode"] == code.value
        assert held_card["reviewConfigs"][0]["hideAllowAlways"] is True

    @_OTHER_ASKS
    async def test_the_other_asks_are_still_approved(self, workspace: Path, make: Callable[[Path], ToolCall]) -> None:
        call = make(workspace)

        approved, denied, pending = await _evaluate(_YOLO, [call], workspace)

        assert ([item[1] for item in approved], denied, pending) == ([call], [], [])


class TestTheReviewerIsKeptOutOfTheWrite:
    @_HUMAN_ONLY
    async def test_it_is_not_asked_and_the_write_waits_for_a_person(
        self, workspace: Path, make: Callable[[Path], ToolCall], code: ApprovalReasonCode
    ) -> None:
        reviewer, call = _allow_reviewer(), make(workspace)

        with patch(_REVIEWER, reviewer):
            approved, denied, pending = await _evaluate(_DEFAULT, [call], workspace)

        assert (approved, denied) == ([], [])
        assert [item[1] for item in pending] == [call]
        assert isinstance(pending[0][3], CodedReason)
        assert pending[0][3].code == code
        reviewer.review.assert_not_awaited()

    @_OTHER_ASKS
    async def test_it_is_still_asked_about_the_other_asks(
        self, workspace: Path, make: Callable[[Path], ToolCall]
    ) -> None:
        reviewer, call = _allow_reviewer(), make(workspace)

        with patch(_REVIEWER, reviewer):
            approved, denied, pending = await _evaluate(_DEFAULT, [call], workspace)

        assert ([item[1] for item in approved], denied, pending) == ([call], [], [])
        reviewer.review.assert_awaited_once()


class TestAnExpirySetToAllowStopsShortOfTheWrite:
    @staticmethod
    async def expiry(workspace: Path, calls: list[ToolCall], configured: str = "allow") -> str:
        """What the approval card tells every timer to do with *calls* when its expiry is set to *configured*."""
        with patch(_REVIEWER, None):
            _approved, _denied, pending = await _evaluate(_DEFAULT, calls, workspace)
        payload, _ = build_interrupt_payload(pending, "human-only", timeout_behavior=configured)
        return str(payload["extensions"]["timeout"]["behavior"])

    @_HUMAN_ONLY_CALLS
    async def test_a_write_only_a_person_may_answer_expires_into_a_denial(
        self, workspace: Path, make: Callable[[Path], ToolCall]
    ) -> None:
        assert await self.expiry(workspace, [make(workspace)]) == "deny"

    @pytest.mark.parametrize("command", ["git push origin main", "rm -rf ./build"], ids=["social", "destructive"])
    async def test_an_irreversible_call_expires_into_a_denial(self, workspace: Path, command: str) -> None:
        assert await self.expiry(workspace, [_shell(command)]) == "deny"

    async def test_one_such_call_turns_the_whole_batch(self, workspace: Path) -> None:
        calls = [_shell("curl http://unlisted.example/x"), _file_write(workspace / "AGENTS.md")]

        assert await self.expiry(workspace, calls) == "deny"

    @pytest.mark.parametrize(
        "make",
        [
            pytest.param(lambda _ws: _charge(), id="payment-guarded-by-its-digest"),
            pytest.param(lambda _ws: _shell("curl http://unlisted.example/x"), id="ordinary-ask"),
            pytest.param(lambda ws: _file_write(ws.parent / "outside" / "notes.txt"), id="outside-the-zones"),
        ],
    )
    async def test_every_other_ask_keeps_the_configured_expiry(
        self, workspace: Path, make: Callable[[Path], ToolCall]
    ) -> None:
        assert await self.expiry(workspace, [make(workspace)]) == "allow"

    async def test_an_expiry_set_to_deny_stays_deny(self, workspace: Path) -> None:
        assert await self.expiry(workspace, [_shell("curl http://unlisted.example/x")], configured="deny") == "deny"
