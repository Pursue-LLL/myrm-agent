"""The analyzer judges every command a line runs, not only the line as written.

A rule written for ``rm -rf ~`` has to fire wherever the shell runs that command: behind a separator it is glued to,
inside a script handed to a shell, behind a prefix such as ``sudo``, in a group or a ``trap`` handler. The script
is read wherever the shell that runs it stands: after ``then``, ``docker exec ctr``, a redirection, a ``case`` arm.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import (
    PROTECTED_WRITE_CATEGORY,
    ThreatLevel,
    analyze_command,
    has_block_threat,
    is_destructive_command,
)

_BLOCKED_BASES = (
    "rm -rf ~",
    "rm -rf /",
    "rm -rf $HOME",
    "rm --force --recursive ~",
    "mkfs.ext4 /dev/sda1",
    "dd if=/dev/zero of=/dev/sda",
    "shutdown now",
    "echo x >> ~/.ssh/authorized_keys",
)
_ESCALATED_BASES = ("kill 123", "pkill node", "eval x")

# The command sits beside another one, glued to a separator or inside a compound command.
_SEPARATOR_FORMS = (
    "{d};echo done",
    "{d} ; echo done",
    "{d}&&echo done",
    "{d}||echo done",
    "{d}|cat",
    "{d}&",
    "{d};",
    "{d}\necho done",
    "echo hi;{d}",
    "echo hi&&{d}",
    "echo hi\n{d}",
    "echo hi|{d}",
    "if true; then {d}; fi",
    "for i in 1 2; do {d}; done",
    "while true; do {d}; done",
    "{{ {d}; }}",
)

# Another command runs it: a script handed to a shell, ``eval``, a prefix, a ``trap`` handler.
_WRAPPER_FORMS = (
    "sh -c '{d}'",
    'sh -c "{d}"',
    "bash -lc '{d}'",
    "/bin/bash -c '{d}'",
    "eval '{d}'",
    'eval "{d}"',
    "sudo {d}",
    "env X=1 {d}",
    "timeout 5 {d}",
    "nohup {d}",
    "xargs {d}",
    "trap '{d}' EXIT",
    'trap "{d}" EXIT',
    "sudo bash -c '{d}'",
    "sh -c 'echo a; {d}'",
    "bash -c '{d}&&echo done'",
    "sh -c 'bash -c \"{d}\"'",
)

# The command sits in a group: the opener and the closer are glued to the words around it, and the two can belong
# to different statements of the line.
_GROUP_FORMS = (
    "({d})",
    "( {d} )",
    "(({d}))",
    "{d})",
    "then ({d})",
    "echo hi && ({d})",
    "(cd /tmp && {d})",
    "(cd /tmp; {d})",
    "if true; then ({d}); fi",
    "{{ ({d}); }}",
    "(sudo {d})",
    "(env X=1 {d})",
)

_FORMS = _SEPARATOR_FORMS + _WRAPPER_FORMS + _GROUP_FORMS

# The shell that runs a script stands behind something no prefix table names: a reserved word, a group, a
# redirection, a command that runs its arguments, a ``case`` arm or a function body.
_CONTEXT_FORMS = (
    "if true; then {w}; fi",
    "if true\nthen {w}\nfi",
    "if true; then echo a; else {w}; fi",
    "for i in 1 2; do {w}; done",
    "while true; do {w}; done",
    "until false; do {w}; done",
    "! {w}",
    "{{ {w}; }}",
    "({w})",
    "( {w} )",
    "2>&1 {w}",
    "docker exec ctr {w}",
    "ssh host {w}",
    "flock lock {w}",
    "find . -exec {w} \\;",
    "case x in x) {w};; esac",
    "f() {{ {w}; }}; f",
)
_SCRIPT_FORMS = ("sh -c '{d}'", 'bash -lc "{d}"', "eval '{d}'", "trap '{d}' EXIT")


def _verdict(command: str) -> set[ThreatLevel]:
    """The levels the rules other than the shell-syntax style policy give *command*."""
    return {threat.level for threat in analyze_command(command) if threat.category != "injection"}


@pytest.mark.parametrize("form", _FORMS)
@pytest.mark.parametrize("base", _BLOCKED_BASES)
def test_a_blocked_command_stays_blocked_in_every_form(base: str, form: str) -> None:
    assert ThreatLevel.BLOCK in _verdict(form.format(d=base))


@pytest.mark.parametrize("form", _FORMS)
@pytest.mark.parametrize("base", _ESCALATED_BASES)
def test_an_escalated_command_stays_escalated_in_every_form(base: str, form: str) -> None:
    assert ThreatLevel.ESCALATE in _verdict(form.format(d=base))


@pytest.mark.parametrize("context", _CONTEXT_FORMS)
@pytest.mark.parametrize("script", _SCRIPT_FORMS)
@pytest.mark.parametrize("base", _BLOCKED_BASES)
def test_a_script_handed_to_a_shell_is_read_wherever_the_shell_stands(base: str, script: str, context: str) -> None:
    assert ThreatLevel.BLOCK in _verdict(context.format(w=script.format(d=base)))


@pytest.mark.parametrize("context", _CONTEXT_FORMS)
def test_a_harmless_script_is_not_blocked_wherever_the_shell_stands(context: str) -> None:
    assert has_block_threat(context.format(w="sh -c 'echo hello'")) is None


@pytest.mark.parametrize(
    "command",
    [
        "ls; pwd",
        "cd build; make",
        "echo a;echo b",
        "for i in 1 2 3; do echo $i; done",
        "if [ -f x ]; then echo y; else echo n; fi",
        "while read line; do echo $line; done < notes.txt",
        "find . -name '*.pyc' -exec rm {} \\;",
        "find . -type f -exec chmod 644 {} \\; && echo done",
        "git log --format=%H; git status",
    ],
)
def test_chaining_with_a_semicolon_is_no_threat_of_its_own(command: str) -> None:
    assert analyze_command(command) == ()


@pytest.mark.parametrize(
    "command",
    [
        "echo 'rm -rf /'",
        "echo 'a; rm -rf ~'",
        "echo 'sudo rm -rf ~' | cat",
        'grep -Ei "rm |rm -|unlink|remove|data/|delete|shred|version|cache" notes.txt',
        "sh -c 'echo hello; ls -la'",
        "bash -c 'echo \"rm -rf build\" > plan.txt'",
        "git commit -m \"docs: sh -c 'rm -rf ~' is blocked\"",
        "echo \"bash -c 'rm -rf ~'\"",
        "trap 'echo cleanup done' EXIT",
        "xargs echo",
        "env FOO=1 python script.py",
        "timeout 5 ls",
    ],
)
def test_quoted_text_and_harmless_wrapped_commands_are_not_blocked(command: str) -> None:
    assert has_block_threat(command) is None


_PREFIXES = ("env", "env X=1", "nohup", "time", "timeout 5", "xargs", "command", "nice -n 5", "watch -n1")
_QUOTED_FORMS = ("echo '{d}'", "git commit -m 'never run {d}'", "grep -rn '{d}' docs/")


@pytest.mark.parametrize("form", _QUOTED_FORMS)
@pytest.mark.parametrize("prefix", _PREFIXES)
@pytest.mark.parametrize("base", _BLOCKED_BASES + _ESCALATED_BASES)
def test_dangerous_text_quoted_behind_a_prefix_is_no_threat(base: str, prefix: str, form: str) -> None:
    """A prefix hands control to the command behind it, so the quoted text of that command stays text."""
    command = f"{prefix} {form.format(d=base)}"
    assert analyze_command(command) == ()
    assert not is_destructive_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "(echo x > uv.lock)",
        "(cd d && echo x > package-lock.json)",
        "(sed -i s/a/b/ yarn.lock)",
    ],
)
def test_a_rule_that_ends_at_a_file_name_sees_through_a_group_closer(command: str) -> None:
    assert has_block_threat(command) is not None


def test_a_threat_found_in_several_readings_is_reported_once() -> None:
    threats = analyze_command("rm -rf ~; sh -c 'rm -rf ~'")
    assert len(threats) == len(set(threats))
    assert [t for t in threats if t.detail == "Deleting home directory"]


def test_the_threat_of_the_line_as_written_comes_first() -> None:
    first = analyze_command("echo $(whoami) && sh -c 'rm -rf ~'")[0]
    assert first.category == "injection"


def test_a_script_handed_to_a_shell_is_read_by_the_sql_guard() -> None:
    threats = analyze_command("sh -c \"psql -c 'DROP TABLE users'\"")
    assert any(t.category == "destructive_sql" and t.level is ThreatLevel.ESCALATE for t in threats)


def test_a_script_handed_to_a_shell_is_read_for_protected_instruction_writes() -> None:
    threats = analyze_command("bash -c 'echo x > AGENTS.md'")
    assert any(t.category == PROTECTED_WRITE_CATEGORY for t in threats)


@pytest.mark.parametrize(
    "command",
    [
        "".join("sh -c '" for _ in range(40)) + "rm -rf ~" + "'" * 40,
        "".join('sh -c "' for _ in range(40)) + "rm -rf ~" + '"' * 40,
        "echo " + "$(echo x) " * 400,
        "; ".join(["sh -c 'echo a'"] * 300),
    ],
    ids=["nested-single-quotes", "nested-double-quotes", "many-substitutions", "many-statements"],
)
def test_a_line_built_to_nest_deeply_or_branch_widely_is_read_within_bounds(command: str) -> None:
    assert isinstance(analyze_command(command), tuple)


@pytest.mark.parametrize(
    "command",
    [
        "A=1 " * 20_000 + "sh -c 'rm -rf ~'",
        "eval " * 20_000 + "rm -rf ~",
        "eval " * 20_000 + "'rm -rf ~'",
        "sh -c 'echo a' " * 20_000,
    ],
    ids=["assignment-run", "eval-chain", "eval-chain-quoted-payload", "many-interpreters"],
)
def test_a_line_built_to_make_the_reading_quadratic_is_read_in_time(command: str) -> None:
    """Each of these is read in well under a second. Trying every word with the assignment-skipping reader costs
    tens of seconds on the assignment run, and re-expanding every nested script costs as long on the ``eval`` chain,
    so the bound separates the two without being close to either on an idle machine."""
    started = time.monotonic()
    analyze_command(command)
    assert time.monotonic() - started < 10.0


def test_a_script_behind_a_long_assignment_run_is_still_read() -> None:
    assert has_block_threat("A=1 " * 5_000 + "sh -c 'rm -rf ~'") is not None


def test_a_shell_script_behind_a_long_chain_of_evals_is_still_read() -> None:
    """Only the first ``eval`` is read as a script; the shell word behind the chain is read on its own."""
    assert has_block_threat("eval " * 200 + "sh -c 'rm -rf ~'") is not None


@pytest.mark.parametrize(
    "command",
    [
        "sh -c 'rm -rf build'",
        'bash -c "git reset --hard"',
        "eval 'git clean -fd'",
        "sudo bash -c 'mv a b'",
        "(rm -rf build)",
        "(cd d && git reset)",
        "trap 'rm -rf build' EXIT",
        "echo ok;rm -rf build",
    ],
)
def test_a_destructive_command_is_found_behind_a_wrapper(command: str) -> None:
    assert is_destructive_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "echo 'rm -rf build'",
        "sh -c 'echo hi'",
        "sudo ls",
        "git status; git log --oneline",
        "env echo 'rm -rf build'",
        "timeout 30 grep -rn 'rm -rf /' scripts/",
        "nice git log --grep='git reset --hard'",
    ],
)
def test_a_harmless_command_is_not_destructive_behind_a_wrapper(command: str) -> None:
    assert not is_destructive_command(command)
