"""A shell command that rewrites a protected instruction file stays with a person, whatever approved it.

The file tools report such a write as an ask under a fixed code. The gates that "always allow" must never lift
recognise it by that code (the allowlist stage and the pending-approval annotation), and a scheduled run refuses any
path verdict that is not an allow. The shell tools carry the same verdict for a command line that rewrites one of the
files, so a standing approval of the user cannot carry the rewrite past a person. Verifies, with the real engine and
the real decision stages:
1. The engine asks, under the protected-file code, for the bash tool and for text typed into a process alike, in the
   POSIX, PowerShell and cmd spellings of a write, and a rule that allows the command does not turn that ask into an
   allow.
2. An allowlist entry never covers it, the allow-always guard refuses to remember it, and a read of the same files is
   untouched.
3. A scheduled run refuses it whatever its declaration covers, and still approves a read.
4. A command line is judged command by command: a read beside an unrelated command is not mistaken for a write, and
   a search whose argument spells an edit command is not one either.
5. Python source the bash tool runs in its wrapper is not shell syntax, and this check does not read it; the same text
   started in the background is read by a shell, and is judged.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from unittest.mock import patch

import pytest
from langchain_core.messages import ToolCall

import myrm_agent_harness.agent.security.approval_flow as approval_flow
from myrm_agent_harness.agent.middlewares.approval._allow_always import should_block_allow_always
from myrm_agent_harness.agent.middlewares.approval.batch_processor import evaluate_tool_batch
from myrm_agent_harness.agent.middlewares.approval.helpers import reset_denial_counter
from myrm_agent_harness.agent.security.approval_flow import DEFAULT_USER_ID, AllowlistEntry
from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode, CodedReason
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.engine import evaluate_tool_call, merge
from myrm_agent_harness.agent.security.guards.taint_tracker import reset_taint_tracker
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)
from myrm_agent_harness.agent.security.workspace_trust.context import clear_workspace_trust_context

_ALLOWLIST_AUDIT = "myrm_agent_harness.agent.middlewares.approval.batch_processor.decide.allowlist.record_decision"
_PROTECTED = "Protected instruction file write requires human approval"
_BLOCKED = "PROTECTED_INSTRUCTION_ALLOWLIST_BLOCKED"
_DUAL_INSURANCE = "BATCH_RISK_DUAL_INSURANCE_ESCALATED"
ASK, ALLOW, DENY = PermissionAction.ASK, PermissionAction.ALLOW, PermissionAction.DENY
_ASK_EVERYTHING = SecurityConfig(ruleset=DEFAULT_RULESET)

Batch = tuple[
    list[tuple[int, ToolCall]],
    list[tuple[int, ToolCall, str]],
    list[tuple[int, ToolCall, str, str, dict[str, object] | None]],
]

# Each command line that rewrites a protected file, with the file name the engine reports. None of them trips a block
# category, so the bash tool and text typed into a process reach the same ask.
_WRITES = (
    ("echo x > AGENTS.md", "AGENTS.md"),
    ("echo x >> ./docs/SOUL.md", "SOUL.md"),
    ("cat notes | tee -a CLAUDE.md", "CLAUDE.md"),
    ("cp backdoor.md MEMORY.md", "MEMORY.md"),
    ("mv draft.md .clinerules", ".clinerules"),
    ("rm -f AGENTS.md", "AGENTS.md"),
    ("rm -rf .cursor/rules", ".cursor/rules"),
    ("truncate -s 0 .windsurfrules", ".windsurfrules"),
    ("cd repo && echo x >> agents.md", "agents.md"),
    ("bash -c 'echo x >> AGENTS.md'", "AGENTS.md"),
    ("cat <<'EOF' > AGENTS.md\nhello\nEOF", "AGENTS.md"),
    ("ls && echo x > AGENTS.md", "AGENTS.md"),
    ("echo ok | tee .github/copilot-instructions.md", ".github/copilot-instructions.md"),
    ("echo x >& AGENTS.md", "AGENTS.md"),
    ("sed -n -i 's/strict/lax/' SOUL.md", "SOUL.md"),
    ("sed --in-place 's/strict/lax/' AGENTS.md", "AGENTS.md"),
    ("(cd repo && cp backdoor.md AGENTS.md)", "AGENTS.md"),
    ("Set-Content -Path AGENTS.md -Value x", "AGENTS.md"),
    ("Add-Content -Path docs/SOUL.md -Value x", "SOUL.md"),
    ("Remove-Item -Force .cursor/rules", ".cursor/rules"),
    ("Copy-Item backdoor.md MEMORY.md", "MEMORY.md"),
    ("copy backdoor.md AGENTS.md", "AGENTS.md"),
    ("del .\\SOUL.md", "SOUL.md"),
    ("echo x > .\\AGENTS.md", "AGENTS.md"),
    ("cp backdoor.md C:\\work\\CLAUDE.md", "CLAUDE.md"),
    ("Set-Content -Path .cursor\\rules\\style.mdc -Value x", ".cursor/rules"),
    ('powershell -NoProfile -ExecutionPolicy Bypass -Command "del .\\SOUL.md"', "SOUL.md"),
    ('cmd /c "cd repo && del AGENTS.md"', "AGENTS.md"),
    # A python interpreter the wrapper does not run as Python source (an option between it and ``-c``, a versioned
    # name) is a shell command like any other.
    ("python3 -u -c \"open('AGENTS.md', 'w').write('x')\"", "AGENTS.md"),
    ("python -u -c \"open('AGENTS.md', 'w').write('x')\"", "AGENTS.md"),
    ('python3.12 -c "print(1)" | tee AGENTS.md', "AGENTS.md"),
)
# Forms a block category stops when they are typed into a process, while the bash tool reaches the ask.
_BASH_ONLY_WRITES = (
    ("sed -i 's/strict/lax/' .cursorrules", ".cursorrules"),
    ("node -e \"require('fs').writeFileSync('AGENTS.md', 'x')\"", "AGENTS.md"),
    ("ruby -e \"File.write('AGENTS.md', 'x')\"", "AGENTS.md"),
)
# Command lines that only read the files.
_READS = (
    "cat AGENTS.md",
    "head -n 20 SOUL.md",
    "grep -n rule .cursorrules",
    "git diff -- AGENTS.md",
    "ls docs && cat AGENTS.md | wc -l",
    "echo AGENTS.md is a great file",
    "grep -n rm AGENTS.md",
    "rg tee CLAUDE.md",
    "git grep -n 'rm ' -- AGENTS.md",
    "Get-Content .\\AGENTS.md -Tail 20",
)
# Reads next to a command that writes something else: judged command by command, they are not writes either.
_READS_BESIDE_OTHER_WRITES = (
    "rm -rf build && cat AGENTS.md",
    "cp a.txt b.txt && head SOUL.md",
    "mv old.log new.log | grep AGENTS.md",
)
# Python source the bash tool runs in its wrapper, opening a protected file for writing.
_PYTHON_REWRITE = "python3 -c \"open('AGENTS.md', 'w').write('x')\""
_BASH, _STDIN = ("code_interpreter", "command"), ("shell_exec", "data")
_SHELL_TOOLS = pytest.mark.parametrize(("permission", "key"), [_BASH, _STDIN], ids=["bash-tool", "typed-into-process"])


def bash_call(command: str) -> ToolCall:
    return ToolCall(type="tool_call", name="bash_code_execute_tool", args={"command": command}, id="c1")


def stdin_call(data: str) -> ToolCall:
    args: dict[str, object] = {"action": "submit_stdin", "pid": 7, "data": data}
    return ToolCall(type="tool_call", name="bash_process_tool", args=args, id="c1")


# A scheduled run declares the capabilities it may use; text typed into a process needs ``shell_exec`` declared too.
_CRON_TOOLS = pytest.mark.parametrize(
    ("call_of", "declared"),
    [(bash_call, ("code_interpreter",)), (stdin_call, ("code_interpreter", "shell_exec"))],
    ids=["bash-tool", "typed-into-process"],
)


def config_with(*rules: PermissionRule) -> SecurityConfig:
    """The default rules plus *rules*; later rules win, as for a user profile."""
    return SecurityConfig(ruleset=merge(DEFAULT_RULESET, rules))


async def judge(
    call: ToolCall, *, config: SecurityConfig = _ASK_EVERYTHING, is_cron: bool = False
) -> tuple[Batch, list[str]]:
    """The batch verdict for *call* and the audit labels the allowlist stage wrote while reaching it."""
    with patch(_ALLOWLIST_AUDIT) as audit:
        batch = await evaluate_tool_batch([call], config, is_cron, "/tmp", "protected-floor", {})
    return batch, [record.args[1] for record in audit.call_args_list]


async def remember(entry: AllowlistEntry) -> None:
    """A standing approval of the user."""
    await approval_flow.get_allowlist().add(DEFAULT_USER_ID, entry)


BASH_TOOL_ENTRY = AllowlistEntry(permission="code_interpreter", tool_name="bash_code_execute_tool")
STDIN_TOOL_ENTRY = AllowlistEntry(permission="shell_exec", tool_name="bash_process_tool")


@pytest.fixture(autouse=True)
def _clean_state() -> Iterator[None]:
    reset_denial_counter()
    reset_taint_tracker()
    approval_flow._allowlist = approval_flow.Allowlist()
    clear_workspace_trust_context()
    yield
    clear_workspace_trust_context()
    reset_taint_tracker()


class TestTheEngineAsksAboutAShellWrite:
    @_SHELL_TOOLS
    @pytest.mark.parametrize(("command", "name"), _WRITES)
    def test_the_ask_carries_the_protected_file_code_and_the_file_name(
        self, permission: str, key: str, command: str, name: str
    ) -> None:
        action, reason = evaluate_tool_call(permission, {key: command}, _ASK_EVERYTHING)

        assert action == ASK
        assert isinstance(reason, CodedReason)
        assert (reason.code, reason.subject) == (ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE, name)
        assert _PROTECTED in reason

    @pytest.mark.parametrize(("command", "name"), _BASH_ONLY_WRITES)
    def test_the_bash_tool_asks_for_what_a_block_category_stops_when_typed_into_a_process(
        self, command: str, name: str
    ) -> None:
        action, reason = evaluate_tool_call("code_interpreter", {"command": command}, _ASK_EVERYTHING)

        assert action == ASK
        assert isinstance(reason, CodedReason)
        assert (reason.code, reason.subject) == (ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE, name)
        assert evaluate_tool_call("shell_exec", {"data": command}, _ASK_EVERYTHING)[0] == DENY

    def test_python_source_the_bash_tool_runs_is_not_read_as_a_shell_write(self) -> None:
        _action, reason = evaluate_tool_call("code_interpreter", {"command": _PYTHON_REWRITE}, _ASK_EVERYTHING)

        assert _PROTECTED not in reason
        assert evaluate_tool_call("shell_exec", {"data": _PYTHON_REWRITE}, _ASK_EVERYTHING)[0] == DENY

    def test_the_same_text_started_in_the_background_is_read_as_a_shell_write(self) -> None:
        tool_input: dict[str, object] = {"command": _PYTHON_REWRITE, "run_in_background": True}

        action, reason = evaluate_tool_call("code_interpreter", tool_input, _ASK_EVERYTHING)

        assert action == ASK
        assert isinstance(reason, CodedReason)
        assert (reason.code, reason.subject) == (ApprovalReasonCode.PROTECTED_INSTRUCTION_WRITE, "AGENTS.md")

    @_SHELL_TOOLS
    def test_a_rule_that_allows_the_command_does_not_allow_the_write(self, permission: str, key: str) -> None:
        config = config_with(PermissionRule(permission, "*", ALLOW))

        assert evaluate_tool_call(permission, {key: "ls -la"}, config)[0] == ALLOW
        action, reason = evaluate_tool_call(permission, {key: "echo x >> AGENTS.md"}, config)

        assert action == ASK
        assert _PROTECTED in reason

    def test_another_ask_on_the_same_line_does_not_hide_it_from_text_typed_into_a_process(self) -> None:
        """``eval`` is an ask of its own; the write beside it is still the one the gates recognise."""
        command = 'eval "echo hi" && echo y >> AGENTS.md'

        action, reason = evaluate_tool_call("shell_exec", {"data": command}, _ASK_EVERYTHING)

        assert action == ASK
        assert _PROTECTED in reason

    def test_a_block_category_still_outranks_the_ask(self) -> None:
        action, reason = evaluate_tool_call("shell_exec", {"data": "sudo cp x AGENTS.md"}, _ASK_EVERYTHING)

        assert action == DENY
        assert _PROTECTED not in reason

    @_SHELL_TOOLS
    @pytest.mark.parametrize("command", _READS + _READS_BESIDE_OTHER_WRITES)
    def test_a_read_is_not_a_write(self, permission: str, key: str, command: str) -> None:
        _action, reason = evaluate_tool_call(permission, {key: command}, _ASK_EVERYTHING)

        assert _PROTECTED not in reason


class TestAStandingApprovalNeverCarriesTheWrite:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(("command", "_name"), _WRITES)
    async def test_an_entry_for_the_bash_tool_does_not_approve_it(self, command: str, _name: str) -> None:
        await remember(BASH_TOOL_ENTRY)
        call = bash_call(command)

        (approved, _denied, pending), labels = await judge(call)

        assert approved == []
        assert [item[1] for item in pending] == [call]
        # A destructive command is escalated by the risk layer before the allowlist is consulted.
        assert labels in ([_BLOCKED], [_DUAL_INSURANCE])

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("command", "_name"), _WRITES)
    async def test_an_entry_for_text_typed_into_a_process_does_not_approve_it(self, command: str, _name: str) -> None:
        await remember(STDIN_TOOL_ENTRY)
        call = stdin_call(command)

        (approved, _denied, pending), labels = await judge(call)

        assert approved == []
        assert [item[1] for item in pending] == [call]
        assert labels == [_BLOCKED]

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("pattern", "command"),
        [
            ("sed -i *", "sed -i 's/strict/lax/' SOUL.md"),
            ("cp *", "cp backdoor.md MEMORY.md"),
            ("tee *", "tee -a CLAUDE.md"),
            ("mv *", "mv draft.md .clinerules"),
            ("Set-Content *", "Set-Content -Path AGENTS.md -Value x"),
            ("copy *", "copy backdoor.md AGENTS.md"),
        ],
    )
    async def test_a_command_pattern_entry_does_not_approve_the_write_it_covers(
        self, pattern: str, command: str
    ) -> None:
        await remember(
            AllowlistEntry(permission="code_interpreter", tool_name="bash_code_execute_tool", command_pattern=pattern)
        )

        (approved, _denied, pending), labels = await judge(bash_call(command))

        assert (approved, len(pending)) == ([], 1)
        assert labels == [_BLOCKED]

    @pytest.mark.asyncio
    async def test_an_ask_of_another_kind_on_the_line_does_not_open_the_entry_to_the_write(self) -> None:
        await remember(STDIN_TOOL_ENTRY)

        (approved, _denied, pending), labels = await judge(stdin_call('eval "echo hi" && echo y >> AGENTS.md'))

        assert (approved, len(pending)) == ([], 1)
        assert labels == [_BLOCKED]

    @pytest.mark.asyncio
    async def test_the_pending_ask_hides_allow_always(self) -> None:
        (_approved, _denied, pending), _labels = await judge(bash_call("echo x >> AGENTS.md"))

        extra_ctx = pending[0][4]
        assert extra_ctx is not None
        assert (extra_ctx["protected_instruction"], extra_ctx["hide_allow_always"]) == (True, True)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", _READS)
    async def test_a_command_that_only_reads_is_approved_whatever_the_entries(self, command: str) -> None:
        await remember(BASH_TOOL_ENTRY)

        (approved, _denied, pending), labels = await judge(bash_call(command))

        assert (len(approved), pending) == (1, [])
        assert _BLOCKED not in labels


class TestAScheduledRunRefusesTheWrite:
    @_CRON_TOOLS
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "command",
        ["sed -i 's/strict/lax/' AGENTS.md", "echo x >> SOUL.md", "Set-Content -Path .\\AGENTS.md -Value x"],
    )
    async def test_a_declared_capability_does_not_approve_it(
        self, call_of: Callable[[str], ToolCall], declared: tuple[str, ...], command: str
    ) -> None:
        config = build_channel_security_config("cron", declared_capabilities=declared)

        (approved, denied, pending), _labels = await judge(call_of(command), config=config, is_cron=True)

        assert (approved, pending) == ([], [])
        assert len(denied) == 1
        assert _PROTECTED in denied[0][2]

    @_CRON_TOOLS
    @pytest.mark.asyncio
    @pytest.mark.parametrize("command", ["cat AGENTS.md", "grep -n rm AGENTS.md", "rg tee CLAUDE.md"])
    async def test_the_same_declaration_still_approves_a_read(
        self, call_of: Callable[[str], ToolCall], declared: tuple[str, ...], command: str
    ) -> None:
        config = build_channel_security_config("cron", declared_capabilities=declared)

        (approved, denied, pending), _labels = await judge(call_of(command), config=config, is_cron=True)

        assert (len(approved), denied, pending) == (1, [], [])


class TestTheAllowAlwaysGuardReadsTheSameCommandLine:
    @pytest.mark.parametrize(("command", "_name"), _WRITES)
    def test_it_refuses_to_remember_a_write(self, command: str, _name: str) -> None:
        bash: dict[str, object] = {"name": "bash_code_execute_tool", "args": {"command": command}}
        stdin: dict[str, object] = {
            "name": "bash_process_tool",
            "args": {"action": "submit_stdin", "pid": 7, "data": command},
        }

        assert should_block_allow_always(bash, None)
        assert should_block_allow_always(stdin, None)

    @pytest.mark.parametrize("command", _READS + _READS_BESIDE_OTHER_WRITES)
    def test_it_remembers_a_command_that_only_reads(self, command: str) -> None:
        assert not should_block_allow_always({"name": "bash_code_execute_tool", "args": {"command": command}}, None)
