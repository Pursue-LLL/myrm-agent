"""A command prefix a trusted workspace declares approves the command a call starts, and nothing else.

The repository lists prefixes in ``.myrm/config.toml`` and the user sees them when trusting the folder. The allowlist
stage reads a covering prefix as it reads a covering allowlist entry: the gates "always allow" must never lift and the
organization policy that ignores the allowlist apply to it as they do to an entry.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolCall

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares._session_context import (
    set_agent_primary_model_slug,
    set_managed_approval_policy,
)
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID, AllowlistEntry
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.guards.taint_tracker import TaintLabel, get_taint_tracker, reset_taint_tracker
from myrm_agent_harness.agent.security.managed_approval_policy import ManagedApprovalPolicy
from myrm_agent_harness.agent.security.types import DEFAULT_RULESET, ReviewDecision, ReviewResult, SecurityConfig
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

_ALLOWLIST_AUDIT = "myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.allowlist.record_decision"
_REVIEWER = "myrm_agent_harness.agent.middlewares.approval._batch_review._security_reviewer"
_PREFIX = "deploy-tool push"
_DEPLOY = "deploy-tool push prod"
_DECLARED = "REPO_PREFIX_AUTO_APPROVE"
_ASK_EVERYTHING = SecurityConfig(ruleset=DEFAULT_RULESET)

Batch = tuple[
    list[tuple[int, ToolCall]],
    list[tuple[int, ToolCall, str]],
    list[tuple[int, ToolCall, str, str, dict[str, object] | None]],
]


def bash_call(command: str, call_id: str = "c1", **args: object) -> ToolCall:
    return ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": command, **args}, id=call_id)


def stdin_call(data: str) -> ToolCall:
    args: dict[str, object] = {"action": "submit_stdin", "pid": 7, "data": data}
    return ToolCall(type="tool_call", name="bash_process_tool", args=args, id="c1")


def declare(*prefixes: str, level: WorkspaceTrustLevel | None = WorkspaceTrustLevel.TRUSTED) -> None:
    """Bind what a run of a workspace with this trust level and these declared prefixes sees."""
    set_workspace_trust_level(level)
    set_repo_command_prefixes(prefixes)


async def judge(
    *calls: ToolCall, config: SecurityConfig = _ASK_EVERYTHING, is_cron: bool = False
) -> tuple[Batch, list[str]]:
    """The batch verdict and the audit labels the allowlist stage wrote while reaching it."""
    with patch(_ALLOWLIST_AUDIT) as audit:
        batch = await evaluate_tool_batch(list(calls), config, is_cron, "/tmp", "repo-prefix", {})
    return batch, [record.args[1] for record in audit.call_args_list]


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_taint_tracker()
    approval_flow._allowlist = approval_flow.Allowlist()
    clear_workspace_trust_context()
    yield
    clear_workspace_trust_context()
    set_managed_approval_policy(None)
    set_agent_primary_model_slug("")
    reset_taint_tracker()


class TestAPrefixApprovesTheCommandItCovers:
    @pytest.mark.asyncio
    async def test_the_command_is_approved_and_audited_as_a_declared_prefix(self) -> None:
        declare(_PREFIX)
        call = bash_call(_DEPLOY)

        (approved, denied, pending), labels = await judge(call)

        assert (approved, denied, pending) == ([(0, call)], [], [])
        assert labels == [_DECLARED]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("command", "covered"),
        [
            ("deploy-tool push", True),
            ("deploy-tool push prod --force", True),
            ("deploy-tool pushing prod", False),
            ("deploy-tool pull prod", False),
            ("sudo deploy-tool push prod", False),
        ],
    )
    async def test_a_prefix_covers_whole_leading_words_only(self, command: str, covered: bool) -> None:
        declare(_PREFIX)

        (approved, _denied, pending), _labels = await judge(bash_call(command))

        assert (len(approved), len(pending)) == ((1, 0) if covered else (0, 1))

    @pytest.mark.asyncio
    async def test_an_allowlist_entry_is_credited_before_a_prefix(self) -> None:
        declare(_PREFIX)
        entry = AllowlistEntry(
            permission="code_interpreter", tool_name="bash_code_execute_tool", command_pattern="deploy-tool push *"
        )
        await approval_flow.get_allowlist().add(DEFAULT_USER_ID, entry)

        (approved, _denied, _pending), labels = await judge(bash_call(_DEPLOY))

        assert len(approved) == 1
        assert labels == ["ALLOWLIST_AUTO_APPROVE"]


class TestAPrefixDoesNotApproveWhatItDoesNotCover:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("level", [WorkspaceTrustLevel.RESTRICTED, WorkspaceTrustLevel.REVOKED, None])
    async def test_only_a_trusted_workspace_has_its_prefixes_honored(self, level: WorkspaceTrustLevel | None) -> None:
        declare(_PREFIX, level=level)

        (approved, _denied, pending), labels = await judge(bash_call(_DEPLOY))

        assert (len(approved), len(pending)) == (0, 1)
        assert _DECLARED not in labels

    @pytest.mark.asyncio
    async def test_a_trusted_workspace_that_declares_nothing_approves_nothing(self) -> None:
        declare()

        (approved, _denied, pending), _labels = await judge(bash_call(_DEPLOY))

        assert (len(approved), len(pending)) == (0, 1)

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command",
        [
            f"{_DEPLOY}; rm -rf build",
            f"{_DEPLOY} && rm -rf build",
            f"{_DEPLOY} | tee deploy.log",
            f"{_DEPLOY} $(rm -rf build)",
            f"{_DEPLOY} > ~/.bashrc",
            f"{_DEPLOY}\nrm -rf build",
        ],
    )
    async def test_a_command_that_runs_something_besides_the_prefix_is_not_covered(self, command: str) -> None:
        declare(_PREFIX)

        (approved, _denied, _pending), labels = await judge(bash_call(command))

        assert approved == []
        assert _DECLARED not in labels

    @pytest.mark.asyncio
    async def test_text_typed_into_a_running_process_is_not_a_launch(self) -> None:
        declare(_PREFIX)

        (approved, _denied, pending), labels = await judge(stdin_call(_DEPLOY))

        assert (len(approved), len(pending)) == (0, 1)
        assert _DECLARED not in labels

    @pytest.mark.asyncio
    async def test_a_tool_that_is_not_the_shell_is_not_covered_for_having_a_command_argument(self) -> None:
        declare(_PREFIX)
        call = ToolCall(type="tool_call", name="mcp__runner__run", args={"command": _DEPLOY}, id="c1")

        (approved, _denied, pending), labels = await judge(call)

        assert (len(approved), len(pending)) == (0, 1)
        assert _DECLARED not in labels


class TestTheGatesAnAllowlistCannotLiftAlsoHoldAgainstAPrefix:
    @pytest.mark.asyncio
    async def test_a_batch_with_a_high_risk_item_approves_none_of_its_commands(self) -> None:
        declare(_PREFIX)

        (approved, _denied, pending), labels = await judge(bash_call("rm -rf build", "c1"), bash_call(_DEPLOY, "c2"))

        assert (approved, len(pending)) == ([], 2)
        assert "BATCH_RISK_DUAL_INSURANCE_ESCALATED" in labels
        assert _DECLARED not in labels

    @pytest.mark.asyncio
    async def test_an_irreversible_social_action_stays_with_a_person(self) -> None:
        declare("git push")

        (approved, _denied, pending), labels = await judge(bash_call("git push origin main"))

        assert (approved, len(pending)) == ([], 1)
        assert labels == ["IRREVERSIBLE_ACTION_ALLOWLIST_BLOCKED"]

    @pytest.mark.asyncio
    async def test_a_financial_spend_stays_with_a_person(self) -> None:
        declare(_PREFIX)

        (approved, _denied, pending), labels = await judge(bash_call(_DEPLOY, amount=100))

        assert (approved, len(pending)) == ([], 1)
        assert labels == ["FINANCIAL_GATE_ALLOWLIST_BLOCKED"]

    @pytest.mark.asyncio
    async def test_a_protected_instruction_write_stays_with_a_person(self) -> None:
        declare("sed -i")

        (approved, _denied, pending), labels = await judge(bash_call("sed -i 's/strict/lax/' AGENTS.md"))

        assert (approved, len(pending)) == ([], 1)
        assert labels == ["PROTECTED_INSTRUCTION_ALLOWLIST_BLOCKED"]

    @pytest.mark.asyncio
    async def test_an_organization_that_ignores_the_allowlist_for_the_model_ignores_the_prefix(self) -> None:
        declare(_PREFIX)
        set_managed_approval_policy(ManagedApprovalPolicy.from_mapping({"ignoreAllowlistForModels": ["gpt-*"]}))
        set_agent_primary_model_slug("gpt-4o")

        (approved, _denied, pending), labels = await judge(bash_call(_DEPLOY))

        assert (approved, len(pending)) == ([], 1)
        assert labels == ["MAP_ALLOWLIST_SKIPPED"]

    @pytest.mark.asyncio
    async def test_the_same_policy_leaves_the_prefix_alone_for_another_model(self) -> None:
        declare(_PREFIX)
        set_managed_approval_policy(ManagedApprovalPolicy.from_mapping({"ignoreAllowlistForModels": ["gpt-*"]}))
        set_agent_primary_model_slug("claude-sonnet-4")

        (approved, _denied, _pending), labels = await judge(bash_call(_DEPLOY))

        assert len(approved) == 1
        assert labels == [_DECLARED]


class TestTheChecksAfterTheAllowlistStillSeeAPrefixApproval:
    @pytest.mark.asyncio
    async def test_a_session_that_ingested_network_content_still_asks_a_person(self) -> None:
        declare(_PREFIX)
        get_taint_tracker().record(TaintLabel.EXTERNAL_NETWORK, "https://x.example/page")

        (approved, _denied, pending), labels = await judge(bash_call(_DEPLOY))

        assert (approved, len(pending)) == ([], 1)
        assert labels == [_DECLARED]

    @pytest.mark.asyncio
    async def test_auto_mode_still_has_the_reviewer_look_at_an_approved_command(self) -> None:
        declare(_PREFIX)
        reviewer = AsyncMock()
        reviewer.review = AsyncMock(return_value=ReviewResult(decision=ReviewDecision.DENY, reason="stub verdict"))

        with patch(_REVIEWER, reviewer):
            (approved, _denied, pending), labels = await judge(
                bash_call(_DEPLOY), config=SecurityConfig(ruleset=DEFAULT_RULESET, auto_mode_enabled=True)
            )

        reviewer.review.assert_awaited_once()
        assert reviewer.review.await_args.args[0] == _DEPLOY
        assert (approved, len(pending)) == ([], 1)
        assert labels == [_DECLARED]

    @pytest.mark.asyncio
    async def test_a_chat_channel_keeps_refusing_text_typed_into_a_process(self) -> None:
        declare(_PREFIX)

        (approved, denied, pending), _labels = await judge(
            stdin_call(_DEPLOY), config=build_channel_security_config("telegram")
        )

        assert (approved, len(denied), pending) == ([], 1, [])

    @pytest.mark.asyncio
    async def test_a_scheduled_run_still_refuses_an_integration_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(shell_command_analyzer, "_EXTRA_INTEGRATION_WRITE_PATTERNS", [])
        register_integration_write_patterns(((r"\bacme-cli\s+send\b", "acme send"),))
        declare("acme-cli send")

        (approved, denied, _pending), labels = await judge(
            bash_call("acme-cli send --to a@b.com --subject Hi"),
            config=build_channel_security_config("cron", declared_capabilities=("code_interpreter",)),
            is_cron=True,
        )

        assert labels == [_DECLARED]
        assert (approved, len(denied)) == ([], 1)
