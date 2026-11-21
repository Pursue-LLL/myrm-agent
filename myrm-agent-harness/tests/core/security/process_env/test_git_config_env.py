"""Git's environment configuration never reaches a child process, in whole.

``GIT_CONFIG_COUNT`` with its ``GIT_CONFIG_KEY_<n>`` / ``GIT_CONFIG_VALUE_<n>`` pairs, and ``GIT_CONFIG_PARAMETERS``, give
git configuration that overrides every file, so one ``alias.x=!cmd`` entry runs a program. Dropping only a part of the
group is worse than dropping none: the ``KEY`` wildcard alone removes ``GIT_CONFIG_KEY_<n>`` and leaves git failing on
every command with ``missing config key``.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
from pathlib import Path

import pytest

from myrm_agent_harness.core.security.process_env import (
    EnvInheritPolicy,
    build_isolated_child_env,
    is_non_inheritable_env_var,
    sanitize_env,
)

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="the probe program is a POSIX command")

_GROUP = {
    "GIT_CONFIG_COUNT": "2",
    "GIT_CONFIG_KEY_0": "alias.probe",
    "GIT_CONFIG_VALUE_0": "!true",
    "GIT_CONFIG_KEY_1": "core.pager",
    "GIT_CONFIG_VALUE_1": "cat",
    "GIT_CONFIG_PARAMETERS": "'alias.probe=!true'",
}
# What a host sets to steer git without handing it a program to run.
_STEERING = {
    "GIT_CONFIG_GLOBAL": "/etc/git/global",
    "GIT_CONFIG_SYSTEM": "/etc/git/system",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "Owner",
}


class TestTheGroupIsDroppedWhole:
    @pytest.mark.parametrize("policy", [EnvInheritPolicy.CORE, EnvInheritPolicy.ALL])
    def test_no_name_of_the_group_survives_a_policy(self, policy: EnvInheritPolicy) -> None:
        env = {"PATH": "/usr/bin", "HOME": "/home/user", **_GROUP}

        assert sanitize_env(env, policy) == {"PATH": "/usr/bin", "HOME": "/home/user"}

    @pytest.mark.parametrize(
        "name",
        ["GIT_CONFIG_COUNT", "git_config_count", "Git_Config_Parameters", "GIT_CONFIG_KEY_17", "git_config_value_100"],
    )
    def test_the_names_are_matched_without_regard_to_case_and_for_any_number(self, name: str) -> None:
        assert is_non_inheritable_env_var(name)

    def test_a_half_set_group_is_dropped_too(self) -> None:
        env = {"PATH": "/usr/bin", "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_VALUE_0": "x"}

        assert sanitize_env(env, EnvInheritPolicy.ALL) == {"PATH": "/usr/bin"}

    def test_the_other_git_settings_of_a_host_stay(self) -> None:
        env = {"PATH": "/usr/bin", **_STEERING}

        assert sanitize_env(env, EnvInheritPolicy.ALL) == env

    def test_an_override_cannot_bring_the_group_back(self) -> None:
        child = build_isolated_child_env({"PATH": "/usr/bin"}, extra_env=_GROUP, inherit_policy=EnvInheritPolicy.ALL)

        assert child == {"PATH": "/usr/bin"}

    def test_an_override_of_another_git_name_still_passes(self) -> None:
        child = build_isolated_child_env(
            {"PATH": "/usr/bin"}, extra_env={"GIT_AUTHOR_NAME": "Owner"}, inherit_policy=EnvInheritPolicy.ALL
        )

        assert child == {"PATH": "/usr/bin", "GIT_AUTHOR_NAME": "Owner"}


def _run_git(args: list[str], *, env: dict[str, str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], env=env, cwd=cwd, capture_output=True, text=True, timeout=30, check=False)


@pytest.fixture
def host_env(tmp_path: Path) -> dict[str, str]:
    """A developer machine's environment, with none of its own git settings and an empty home."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(HOME=str(tmp_path / "home"), GIT_CONFIG_NOSYSTEM="1")
    return env


class TestGitUnderTheHostGroup:
    """Real git: what the child gets is what decides, so these run the program the sanitized environment is for."""

    def test_git_runs_when_the_host_sets_a_group_with_a_name_missing(
        self, tmp_path: Path, host_env: dict[str, str]
    ) -> None:
        host = {**host_env, "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_VALUE_0": "x"}
        if _run_git(["init", "-q", "raw"], env=host, cwd=tmp_path).returncode == 0:
            pytest.skip("this git ignores a group whose KEY_<n> is missing")

        isolated = build_isolated_child_env(host, inherit_policy=EnvInheritPolicy.ALL)
        result = _run_git(["init", "-q", "isolated"], env=isolated, cwd=tmp_path)

        assert result.returncode == 0, result.stderr

    @pytest.mark.parametrize("style", ["numbered pairs", "parameters"])
    def test_the_group_cannot_make_git_run_a_program(
        self, tmp_path: Path, host_env: dict[str, str], style: str
    ) -> None:
        marker = tmp_path / "ran"
        program = f"!touch {shlex.quote(str(marker))}"
        if style == "numbered pairs":
            steering = {"GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "alias.probe", "GIT_CONFIG_VALUE_0": program}
        else:
            steering = {"GIT_CONFIG_PARAMETERS": shlex.quote(f"alias.probe={program}")}
        host = {**host_env, **steering}
        _run_git(["probe"], env=host, cwd=tmp_path)
        if not marker.exists():
            pytest.skip("this git does not read configuration from that variable")
        marker.unlink()

        _run_git(["probe"], env=build_isolated_child_env(host, inherit_policy=EnvInheritPolicy.ALL), cwd=tmp_path)

        assert not marker.exists()
