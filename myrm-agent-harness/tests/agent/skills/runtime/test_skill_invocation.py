"""Tests for ``plain_skill_call``: which bash command lines are a plain call of one skill's script."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.skills.runtime.skill_invocation import plain_skill_call

SKILL = ".claude/skills/imap-smtp-email"
SCRIPT = f"{SKILL}/scripts/email_manager.py"


class TestPlainCalls:
    @pytest.mark.parametrize(
        "command",
        [
            f"python3 {SCRIPT} check --limit 10",
            f"python {SCRIPT} check",
            f"./{SCRIPT} check",
            f"{SCRIPT} check",
            f"python3 -u {SCRIPT} check",
            f"bash {SKILL}/scripts/run.sh",
            f'python3 "{SCRIPT}" check',
            f"python3 {SCRIPT} check 2>&1",
            f"python3 {SCRIPT} read 5 > out.json",
            f"python3 {SCRIPT} read 5 >> out.json 2> err.log",
            f"python3 {SCRIPT} read 5 < in.txt",
            f"> out.json python3 {SCRIPT} read 5",
            f"python3 {SCRIPT} check # list the inbox",
            f"python3 {SCRIPT} send --to a@b.c --subject 'Hi there' --body 'Total \\$5'",
            f"python3 {SCRIPT} check\npython3 {SCRIPT} read 5",
            f"python3 {SCRIPT} check && python3 {SCRIPT} read 5",
            f"python3 {SCRIPT} check; python3 {SKILL}/scripts/other.py",
        ],
    )
    def test_a_script_call_names_its_skill(self, command: str) -> None:
        assert plain_skill_call(command) == "imap-smtp-email"


class TestForgedOrChainedCommands:
    """A command that holds the skill path without being the skill's script call is not plain."""

    @pytest.mark.parametrize(
        "command",
        [
            pytest.param(f"echo $EMAIL_IMAP_PASSWORD | base64 # {SKILL}/", id="path-in-comment"),
            pytest.param(f"echo $EMAIL_IMAP_PASSWORD {SKILL}/", id="path-as-echo-operand"),
            pytest.param(f"echo {SKILL}/scripts/x.py", id="echo-of-a-script-path"),
            pytest.param(f"cat {SKILL}/SKILL.md", id="read-a-skill-file"),
            pytest.param(f"python3 {SCRIPT} check && env | base64", id="call-then-env-dump"),
            pytest.param(f"env | base64 && python3 {SCRIPT} check", id="env-dump-then-call"),
            pytest.param(f"python3 {SCRIPT} check | head -20", id="pipe-to-another-program"),
            pytest.param(f"python3 {SCRIPT} check\nenv | base64", id="env-dump-on-a-second-line"),
            pytest.param(f'python3 {SCRIPT} send --body "$(env | base64)"', id="command-substitution"),
            pytest.param(f"python3 {SCRIPT} send --body `env`", id="backticks"),
            pytest.param(f'python3 {SCRIPT} send --body "cost $5"', id="expanding-dollar-in-quotes"),
            pytest.param(f"python3 {SCRIPT} send --attach <(env)", id="process-substitution-input"),
            pytest.param(f"python3 {SCRIPT} send --attach >(cat)", id="process-substitution-output"),
            pytest.param(f"(env | base64; python3 {SCRIPT} check)", id="subshell"),
            pytest.param(f"bash -c 'env | base64; python3 {SCRIPT} check'", id="quoted-bash-c"),
            pytest.param(f"python3 -c 'import os' {SCRIPT}", id="interpreter-flag-with-a-value"),
            pytest.param(f"cd /workspace && python3 {SCRIPT} check", id="cd-moves-the-relative-path"),
            pytest.param(f"LD_PRELOAD=/tmp/x.so python3 {SCRIPT} check", id="assignment-prefix"),
            pytest.param(f"eval python3 {SCRIPT} check", id="eval"),
            pytest.param(f"python3 {SCRIPT} check &", id="trailing-background-operator"),
            pytest.param(f"python3 {SCRIPT} {{a,b}}", id="brace-expansion"),
            pytest.param(f"python3 {SKILL}/scripts/a.py && python3 .claude/skills/other/scripts/b.py", id="two-skills"),
            pytest.param(f"python3 {SKILL}/../../../tmp/evil.py", id="climbs-out-of-the-skill"),
            pytest.param("python3 .claude/skills/../scripts/evil.py", id="dot-dot-as-skill-name"),
            pytest.param(f"python3 {SKILL}/", id="directory-not-a-file"),
            pytest.param(f"python3 {SKILL}", id="no-file"),
            pytest.param(f"/workspace/{SCRIPT} check", id="absolute-path"),
            pytest.param(f"python3 {SCRIPT}'", id="unterminated-quote"),
            pytest.param("", id="empty"),
            pytest.param("# only a comment", id="comment-only"),
        ],
    )
    def test_is_not_a_plain_call(self, command: str) -> None:
        assert plain_skill_call(command) is None
