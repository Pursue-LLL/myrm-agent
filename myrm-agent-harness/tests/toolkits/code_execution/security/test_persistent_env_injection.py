"""A command cannot leave a code-injection variable set in the persistent shell.

The shell outlives its commands, so ``export BASH_ENV=./x`` or ``export GIT_EXTERNAL_DIFF=./x`` would make a later
``bash -c`` or ``git diff``, which the approval layer treats as read-only, run the script. Setting the variable for one
command only (``NAME=value cmd``) is not persistent; the risk classifier withholds the read-only standing from it.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.code_execution.security.blacklist import (
    CODE_INJECTION_ENV_VARS,
    CORE_SAFE_ENV_VARS,
    DANGEROUS_ENV_PREFIXES,
    DANGEROUS_ENV_VARS,
    is_code_injection_env_name,
)
from myrm_agent_harness.toolkits.code_execution.security.persistent_env import persistent_env_injection
from myrm_agent_harness.toolkits.code_execution.security.shell_command_analyzer import ThreatLevel, analyze_command
from myrm_agent_harness.toolkits.code_execution.security.validator import validate_command


class TestPersistentForms:
    @pytest.mark.parametrize(
        ("command", "name"),
        [
            ("export BASH_ENV=./x.sh", "BASH_ENV"),
            ("export GIT_EXTERNAL_DIFF=./x.sh", "GIT_EXTERNAL_DIFF"),
            ("export GIT_SSH_COMMAND='./x.sh'", "GIT_SSH_COMMAND"),
            ("export LD_PRELOAD=./x.so", "LD_PRELOAD"),
            ("export LD_AUDIT=./x.so", "LD_AUDIT"),
            ("export DYLD_FALLBACK_LIBRARY_PATH=./x", "DYLD_FALLBACK_LIBRARY_PATH"),
            ("export NODE_OPTIONS=--require=./x.js", "NODE_OPTIONS"),
            ("export PYTHONPATH=./x", "PYTHONPATH"),
            ("export PERL5OPT=-Mx", "PERL5OPT"),
            ("export RUBYOPT=-rx", "RUBYOPT"),
            # the way the name is written
            ('export "LD_PRELOAD=./x.so"', "LD_PRELOAD"),
            ("export 'LD_PRELOAD=./x.so'", "LD_PRELOAD"),
            ("export LD_PRELOAD", "LD_PRELOAD"),
            ("export ld_preload=./x.so", "ld_preload"),
            ("export FOO=1 BASH_ENV=./x.sh", "BASH_ENV"),
            ("export -n -p BASH_ENV=./x.sh", "BASH_ENV"),
            ("export  BASH_ENV=./x.sh", "BASH_ENV"),
            ("export BASH_ENV+=./x.sh", "BASH_ENV"),
            # the other builtins that keep a variable for later commands
            ("declare -x BASH_ENV=./x.sh", "BASH_ENV"),
            ("declare -gx BASH_ENV=./x.sh", "BASH_ENV"),
            ("declare -g -x BASH_ENV=./x.sh", "BASH_ENV"),
            ("typeset -x GIT_SSH_COMMAND=./x.sh", "GIT_SSH_COMMAND"),
            ("readonly BASH_ENV=./x.sh", "BASH_ENV"),
            ("command export BASH_ENV=./x.sh", "BASH_ENV"),
            ("builtin export BASH_ENV=./x.sh", "BASH_ENV"),
            # where in the line it stands
            ("cd src && export BASH_ENV=./x.sh", "BASH_ENV"),
            ("echo hi\nexport BASH_ENV=./x.sh", "BASH_ENV"),
            ("ls | export BASH_ENV=./x.sh", "BASH_ENV"),
        ],
    )
    def test_the_injection_variable_is_found(self, command: str, name: str) -> None:
        assert persistent_env_injection(command) == name

    @pytest.mark.parametrize(
        "command",
        [
            "export BASH_ENV=./x.sh",
            'export "GIT_EXTERNAL_DIFF=./x.sh"',
            "declare -x LD_PRELOAD=./x.so",
            "typeset -x BASH_ENV=./x.sh",
            "readonly BASH_ENV=./x.sh",
            "export FOO=1 NODE_OPTIONS=--require=./x.js",
            "bash -c 'export BASH_ENV=./x.sh'",
        ],
    )
    def test_the_validator_denies_it(self, command: str) -> None:
        verdict = validate_command(command, workspace_path="/tmp")

        assert not verdict.is_safe
        assert any(t.level is ThreatLevel.BLOCK for t in analyze_command(command))


class TestOrdinaryCommandsAreLeftAlone:
    @pytest.mark.parametrize(
        "command",
        [
            "export PAGER=less",
            "export EDITOR=vim",
            "export FOO=bar",
            "export LANG=en_US.UTF-8",
            # set in their own shell by people all the time; the host just must not hand them down
            "export CC=clang",
            "export HTTP_PROXY=http://proxy:3128",
            "export PIP_INDEX_URL=https://mirror.example/simple",
            "export ENV=production",
            "export IFS=,",
            "declare FOO=1",
            "declare -a items=(a b)",
            "declare -A table",
            "declare -p BASH_ENV",
            "declare -i BASH_ENV",
            "typeset -i n=1",
            "unset BASH_ENV",
            "export -f deploy",
            # the name is text, not a variable being exported
            "echo export BASH_ENV=./x.sh",
            "git commit -m 'export BASH_ENV=./x.sh'",
            'echo "export LD_PRELOAD=./x.so"',
            "export FOO=BASH_ENV",
            "grep -r BASH_ENV .",
            # one command only, not persistent
            "BASH_ENV=./x.sh bash -c true",
            "env LD_PRELOAD=./x.so true",
        ],
    )
    def test_not_denied(self, command: str) -> None:
        assert persistent_env_injection(command) is None
        assert validate_command(command, workspace_path="/tmp").is_safe

    def test_malformed_quoting_is_not_judged_here(self) -> None:
        assert persistent_env_injection('export "BASH_ENV=./x.sh') is None


class TestTheVariableLists:
    def test_injection_names_are_a_part_of_the_dangerous_ones(self) -> None:
        assert CODE_INJECTION_ENV_VARS < DANGEROUS_ENV_VARS

    def test_the_hosts_blacklist_keeps_every_injection_name_and_the_redirection_ones(self) -> None:
        assert {"LD_PRELOAD", "BASH_ENV", "NODE_OPTIONS", "PYTHONPATH", "PERL5OPT", "RUBYOPT"} <= DANGEROUS_ENV_VARS
        assert {"HTTP_PROXY", "SSL_CERT_FILE", "PIP_INDEX_URL", "CC", "ENV", "IFS"} <= DANGEROUS_ENV_VARS
        assert set(DANGEROUS_ENV_PREFIXES) == {"LD_", "DYLD_", "GIT_SSL_"}

    def test_a_name_a_shell_commonly_sets_is_not_an_injection_name(self) -> None:
        assert not (CODE_INJECTION_ENV_VARS & CORE_SAFE_ENV_VARS)
        for name in ("CC", "CXX", "ENV", "IFS", "HTTP_PROXY", "PIP_INDEX_URL", "PAGER", "EDITOR", "PATH"):
            assert not is_code_injection_env_name(name), name

    @pytest.mark.parametrize("name", ["bash_env", "Git_External_Diff", "LD_ANYTHING", "dyld_whatever", "LD_"])
    def test_names_are_matched_without_regard_to_case_and_by_family(self, name: str) -> None:
        assert is_code_injection_env_name(name)

    @pytest.mark.parametrize("name", ["", "OLD_PRELOAD", "BASH_ENVIRON", "GIT_DIR", "FIELD_X"])
    def test_longer_or_unrelated_names_are_not_matched(self, name: str) -> None:
        assert not is_code_injection_env_name(name)
