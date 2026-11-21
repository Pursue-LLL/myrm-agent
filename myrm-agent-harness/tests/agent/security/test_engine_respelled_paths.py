"""The permission engine judges the file a read opens, not only the spelling the model typed.

``file_read_tool`` opens the on-disk spelling of a path whose quotes, compatibility characters or accents differ from
the file, so the file it opens can be one the typed text does not name. Rules and zones match the typed spelling and
the opened one, and the strictest verdict wins: a respelling can only tighten a decision, never loosen it.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from myrm_agent_harness.agent.security.engine import evaluate_tool_call, merge
from myrm_agent_harness.agent.security.path_rules import check_tool_path_policy
from myrm_agent_harness.agent.security.types import (
    DEFAULT_RULESET,
    PathPolicy,
    PermissionAction,
    PermissionRule,
    SecurityConfig,
)
from myrm_agent_harness.core.security.path import find_existing_unicode_path
from myrm_agent_harness.core.security.tool_registry import strip_read_range

POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="symlink creation needs privileges on Windows")

_SEVERITY = {PermissionAction.ALLOW: 0, PermissionAction.ASK: 1, PermissionAction.DENY: 2}


def _denying(permission: str) -> SecurityConfig:
    """A policy that denies a directory by prefix and a file kind by suffix: both match the typed text only."""
    rules = (
        PermissionRule(permission, "private/*", PermissionAction.DENY),
        PermissionRule(permission, "*.log", PermissionAction.DENY),
    )
    return SecurityConfig(ruleset=merge(DEFAULT_RULESET, rules))


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    root = tmp_path / "ws"
    (root / "private").mkdir(parents=True)
    (root / "private" / "plan.md").write_text("plan")
    (root / "app.log").write_text("log")
    (root / "plan.md").write_text("plan")
    (root / "It's plan.md").write_text("plan")
    (root / ".env").write_text("CANARY=1")
    return root


@pytest.fixture
def home_workspace(tmp_path: Path) -> tuple[Path, SecurityConfig]:
    """A workspace that is the user's home: the forbidden ``.ssh`` directory lies inside it."""
    home = tmp_path / "home"
    (home / ".ssh").mkdir(parents=True)
    (home / ".ssh" / "config").write_text("CANARY=1")
    (home / ".ssh" / ".env").write_text("CANARY=1")
    policy = PathPolicy(forbidden_paths=frozenset({str(home / ".ssh")}), access_roots=())
    return home, SecurityConfig(path_policy=policy)


def _verdict(
    args: dict[str, object],
    workspace: Path,
    config: SecurityConfig | None = None,
    permission: str = "file_read",
) -> tuple[PermissionAction, str]:
    tool_name = "file_read_tool" if permission == "file_read" else "file_write_tool"
    return evaluate_tool_call(
        permission, args, config or SecurityConfig(), workspace_root=str(workspace), tool_name=tool_name
    )


@pytest.mark.parametrize(
    "typed",
    [
        pytest.param('"private/plan.md"', id="prefix-rule-ascii-quotes"),
        pytest.param("\u201cprivate/plan.md\u201d", id="prefix-rule-curly-quotes"),
        pytest.param("'private/plan.md'", id="prefix-rule-single-quotes"),
        pytest.param("`private/plan.md`", id="prefix-rule-backticks"),
        pytest.param("private\uff0fplan.md", id="prefix-rule-fullwidth-solidus"),
        pytest.param('"private/plan.md":1-5', id="prefix-rule-quoted-with-a-line-range"),
        pytest.param('"app.log"', id="suffix-rule-ascii-quotes"),
        pytest.param("app\uff0elog", id="suffix-rule-fullwidth-full-stop"),
    ],
)
def test_a_deny_rule_is_not_dodged_by_respelling_the_path(workspace: Path, typed: str) -> None:
    assert _verdict({"paths": [typed]}, workspace, _denying("file_read"))[0] == PermissionAction.DENY


@pytest.mark.parametrize("exact", ["private/plan.md", "app.log"])
def test_the_deny_rule_still_denies_the_exact_spelling(workspace: Path, exact: str) -> None:
    assert _verdict({"paths": [exact]}, workspace, _denying("file_read"))[0] == PermissionAction.DENY


def test_a_write_opens_the_typed_name_so_only_that_name_is_judged(workspace: Path) -> None:
    config = _denying("file_write")

    # The write creates a file named with the quotes, which no rule names; nothing is respelled for a write.
    assert (
        _verdict({"path": '"app.log"'}, workspace, config, permission="file_write")[0]
        == _verdict({"path": "new.txt"}, workspace, config, permission="file_write")[0]
    )


def test_a_respelling_into_a_forbidden_directory_is_denied(home_workspace: tuple[Path, SecurityConfig]) -> None:
    home, config = home_workspace

    action, reason = _verdict({"paths": ["\uff0e\uff53\uff53\uff48/config"]}, home, config)

    assert action == PermissionAction.DENY
    assert ".ssh/config" in reason


def test_the_strictest_of_the_typed_and_the_respelled_verdict_wins(
    home_workspace: tuple[Path, SecurityConfig],
) -> None:
    home, config = home_workspace

    # ``.env`` is a credential name already (ASK); the forbidden directory is what the respelling adds (DENY).
    assert _verdict({"paths": ["\uff0e\uff53\uff53\uff48/.env"]}, home, config)[0] == PermissionAction.DENY


@POSIX_ONLY
def test_a_respelled_link_to_a_credential_file_asks(workspace: Path) -> None:
    (workspace / "notes.txt").symlink_to(".env")

    action, reason = _verdict({"paths": ["\u201cnotes.txt\u201d"]}, workspace)

    assert action == PermissionAction.ASK
    assert "Sensitive file: .env" in reason


def test_a_typed_credential_name_still_asks(workspace: Path) -> None:
    assert _verdict({"paths": [".env"]}, workspace)[0] == PermissionAction.ASK


def test_a_respelling_of_an_ordinary_file_stays_allowed(workspace: Path) -> None:
    assert _verdict({"paths": ["It\u2019s plan.md"]}, workspace)[0] == PermissionAction.ALLOW


def test_a_respelling_outside_the_allowed_zones_asks_with_the_name_it_opens(tmp_path: Path, workspace: Path) -> None:
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "a.txt").write_text("x")

    action, reason = _verdict({"paths": ['"../outside/a.txt"']}, workspace)

    assert action == PermissionAction.ASK
    assert "../outside/a.txt" in reason


def test_the_cron_policy_judges_the_respelling_too(tmp_path: Path, workspace: Path) -> None:
    (tmp_path / "outside").mkdir()
    (tmp_path / "outside" / "a.txt").write_text("x")

    verdict = check_tool_path_policy("file_read", {"paths": ['"../outside/a.txt"']}, SecurityConfig(), str(workspace))

    assert verdict is not None
    assert verdict[0] == PermissionAction.ASK


@pytest.mark.parametrize(
    "typed",
    [
        '"private/plan.md"',
        "`plan.md`",
        "\u201cplan.md\u201d:1-3",
        "It\u2019s plan.md",
        "\u2018private/plan.md\u2019",
        "private\uff0fplan.md",
        '"app.log"',
    ],
)
def test_the_verdict_is_at_least_as_strict_as_the_one_for_the_file_a_read_opens(workspace: Path, typed: str) -> None:
    opened = find_existing_unicode_path(strip_read_range(typed), base_dir=str(workspace))
    assert opened is not None, "the spelling is meant to be one the read opens as another name"
    config = _denying("file_read")

    judged_typed = _verdict({"paths": [typed]}, workspace, config)[0]
    judged_opened = _verdict({"paths": [opened]}, workspace, config)[0]

    assert _SEVERITY[judged_typed] >= _SEVERITY[judged_opened]
