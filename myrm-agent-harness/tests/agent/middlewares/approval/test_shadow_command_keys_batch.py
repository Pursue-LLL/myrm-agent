"""The approval stages act on the text a shell call runs, not on a key the tool's input model drops.

``bash_process_tool`` types ``data`` into a running process; a model that adds ``command`` or ``code`` beside it
changes nothing the tool does, so nothing the approval layers decide may depend on it. Each case sends the real
stdin shape plus one such key, through the stage that reads the command text.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolCall

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval._allow_always import should_block_allow_always
from myrm_agent_harness.agent.middlewares.approval._cron_policy import CronAskVerdict, cron_never_class
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.tool_registry import resolve_permission_type
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    ReviewDecision,
    ReviewResult,
    SecurityConfig,
)
from myrm_agent_harness.agent.security.workspace_trust.context import (
    clear_workspace_trust_context,
    set_repo_command_prefixes,
    set_workspace_trust_level,
)
from myrm_agent_harness.agent.security.workspace_trust.types import WorkspaceTrustLevel
from myrm_agent_harness.toolkits.code_execution.security import (
    register_integration_write_patterns,
    shell_command_analyzer,
)

SHADOW_KEYS = ("command", "code")
_REVIEWER = "myrm_agent_harness.agent.middlewares.approval._batch_review._security_reviewer"
_VENDOR_SEND = "acme-cli send --to a@b.com --subject Hi"

Pending = list[tuple[int, ToolCall, str, str, dict[str, object] | None]]


def stdin_args(data: str, **ignored: str) -> dict[str, object]:
    """The arguments of a ``submit_stdin`` call, with the extra keys a model may add beside the real ones."""
    return {"action": "submit_stdin", "pid": 7, "data": data, **ignored}


def stdin_call(data: str, **ignored: str) -> ToolCall:
    return ToolCall(type="tool_call", name="bash_process_tool", args=stdin_args(data, **ignored), id="c1")


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_taint_tracker()
    approval_flow._allowlist = approval_flow.Allowlist()
    clear_workspace_trust_context()
    yield
    clear_workspace_trust_context()
    reset_taint_tracker()


@pytest.fixture
def vendor_write_pattern(monkeypatch: pytest.MonkeyPatch) -> None:
    """The business layer injects integration write patterns; register a vendor-neutral one for the test."""
    monkeypatch.setattr(shell_command_analyzer, "_EXTRA_INTEGRATION_WRITE_PATTERNS", [])
    register_integration_write_patterns(((r"\bacme-cli\s+send\b", "acme send"),))


def _reviewer(decision: ReviewDecision) -> AsyncMock:
    reviewer = AsyncMock()
    reviewer.review = AsyncMock(return_value=ReviewResult(decision=decision, reason="stub verdict"))
    return reviewer


async def _batch(
    call: ToolCall, config: SecurityConfig, workspace_root: str = "/tmp"
) -> tuple[list[tuple[int, ToolCall]], list[tuple[int, ToolCall, str]], Pending]:
    return await evaluate_tool_batch([call], config, False, workspace_root, "shadow-keys", {})


def _cron_verdict(tool_input: dict[str, object]) -> CronAskVerdict | None:
    return cron_never_class(
        permission_type=resolve_permission_type("bash_process_tool", tool_input),
        tool_name="bash_process_tool",
        tool_input=tool_input,
        config=SecurityConfig(),
        workspace_root="/tmp",
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow", SHADOW_KEYS)
async def test_a_repo_prefix_in_an_ignored_key_does_not_approve_the_typed_text(shadow: str) -> None:
    """The repo-declared prefixes approve a launch; text typed into a process is not a launch."""
    set_workspace_trust_level(WorkspaceTrustLevel.TRUSTED)
    set_repo_command_prefixes(("deploy-tool",))
    config = SecurityConfig(ruleset=DEFAULT_RULESET)

    approved, denied, pending = await _batch(stdin_call("rm -rf build", **{shadow: "deploy-tool push prod"}), config)

    assert (len(approved), len(denied), len(pending)) == (0, 0, 1)


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow", SHADOW_KEYS)
async def test_the_reviewer_is_shown_the_typed_text_of_an_allowed_call(shadow: str) -> None:
    """A read-only text in an ignored key must not let the call skip the review its real text needs."""
    config = SecurityConfig(
        ruleset=(PermissionRule("shell_exec", "*", PermissionAction.ALLOW),), auto_mode_enabled=True
    )
    reviewer = _reviewer(ReviewDecision.DENY)

    with patch(_REVIEWER, reviewer):
        approved, _denied, pending = await _batch(stdin_call("rm -rf build", **{shadow: "ls"}), config)

    reviewer.review.assert_awaited_once()
    assert reviewer.review.await_args.args[0] == "rm -rf build"
    assert approved == []
    assert len(pending) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow", SHADOW_KEYS)
async def test_the_reviewer_is_shown_the_typed_text_of_an_ask(shadow: str) -> None:
    config = SecurityConfig(ruleset=DEFAULT_RULESET, auto_mode_enabled=True)
    reviewer = _reviewer(ReviewDecision.ALLOW)

    with patch(_REVIEWER, reviewer):
        approved, _denied, _pending = await _batch(stdin_call("rm -rf build", **{shadow: "ls"}), config)

    reviewer.review.assert_awaited_once()
    assert reviewer.review.await_args.args[0] == "rm -rf build"
    assert len(approved) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow", SHADOW_KEYS)
async def test_a_script_typed_into_a_process_is_pinned_for_the_resume_check(shadow: str, tmp_path: Path) -> None:
    script = tmp_path / "deploy.sh"
    script.write_text("echo deploy\n")
    config = SecurityConfig(ruleset=DEFAULT_RULESET)

    _approved, _denied, pending = await _batch(stdin_call("bash deploy.sh", **{shadow: "ls"}), config, str(tmp_path))

    context = pending[0][4]
    assert context is not None
    assert context["script_operand_path"] == str(script.resolve())
    assert context["hide_allow_always"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("shadow", SHADOW_KEYS)
async def test_a_script_named_only_in_an_ignored_key_is_not_pinned(shadow: str, tmp_path: Path) -> None:
    (tmp_path / "deploy.sh").write_text("echo deploy\n")
    config = SecurityConfig(ruleset=DEFAULT_RULESET)

    _approved, _denied, pending = await _batch(stdin_call("y", **{shadow: "bash deploy.sh"}), config, str(tmp_path))

    context = pending[0][4]
    assert context is None or "script_operand_path" not in context


@pytest.mark.usefixtures("vendor_write_pattern")
@pytest.mark.parametrize("shadow", SHADOW_KEYS)
class TestAnIntegrationWriteIsFoundInTheTypedText:
    def test_a_cron_run_refuses_it(self, shadow: str) -> None:
        verdict = _cron_verdict(stdin_args(_VENDOR_SEND, **{shadow: "ls"}))

        assert verdict is not None
        assert verdict.audit_reason == "cron fail-closed: integration write mutation"

    def test_a_cron_run_does_not_refuse_text_in_an_ignored_key(self, shadow: str) -> None:
        assert _cron_verdict(stdin_args("y", **{shadow: _VENDOR_SEND})) is None

    def test_allow_always_is_never_written_for_it(self, shadow: str) -> None:
        call = {"name": "bash_process_tool", "args": stdin_args(_VENDOR_SEND, **{shadow: "ls"})}

        assert should_block_allow_always(call, None) is True

    def test_allow_always_is_not_blocked_by_text_in_an_ignored_key(self, shadow: str) -> None:
        call = {"name": "bash_process_tool", "args": stdin_args("y", **{shadow: _VENDOR_SEND})}

        assert should_block_allow_always(call, None) is False


@pytest.mark.parametrize("shadow", ["code", "data"])
def test_allow_always_guards_read_the_command_of_the_shell_tool_alone(shadow: str) -> None:
    protected = {"name": "bash_code_execute_tool", "args": {"command": "rm -f AGENTS.md", shadow: "ls"}}
    harmless = {"name": "bash_code_execute_tool", "args": {"command": "ls", shadow: "rm -f AGENTS.md"}}

    assert should_block_allow_always(protected, None) is True
    assert should_block_allow_always(harmless, None) is False
