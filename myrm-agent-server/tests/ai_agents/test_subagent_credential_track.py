"""A sub-agent delegated from a turn lists its skills for the credential track of that turn.

A delegated custom agent runs inside the delegating turn and is handed that turn's credentials, so a skill that needs
the owner's credential must not be offered to it on a team-shared turn. The only place that knows the track is the
turn's agent builder, which tells the catalog through the extension. These tests pin that hand-over in the source:
the catalog, the factory and the skill backend are exercised on the real path by
`tests/integration/skills/test_google_workspace_oauth_integration.py`.
"""

import ast
from pathlib import Path

import pytest


def _called_name(call: ast.Call) -> str | None:
    """The class name of `Name(...)` and `module.Name(...)`; an import alias cannot be followed."""
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def _is_a_literal_track(value: ast.expr) -> bool:
    """A constant or an enum member written at the call site is a decision made there, not the turn's track."""
    if isinstance(value, ast.Constant):
        return True
    return isinstance(value, ast.Attribute) and isinstance(value.value, ast.Name) and value.value.id == "CredentialTrack"


def _passes_the_turns_track(call: ast.Call) -> bool:
    return any(keyword.arg == "credential_track" and not _is_a_literal_track(keyword.value) for keyword in call.keywords)


def _extension_calls_missing_the_track(app_dir: Path) -> list[str]:
    missing: list[str] = []
    for source in app_dir.rglob("*.py"):
        relative = source.relative_to(app_dir.parent).as_posix()
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Call)
                and _called_name(node) == "SubagentManagementExtension"
                and not _passes_the_turns_track(node)
            ):
                missing.append(f"{relative}:{node.lineno}")
    return missing


def test_every_production_subagent_extension_gets_the_turns_credential_track() -> None:
    """A new place that attaches delegation to a turn must pass that turn's track instead of silently defaulting."""
    assert _extension_calls_missing_the_track(Path(__file__).resolve().parents[2] / "app") == []


@pytest.mark.parametrize(
    "call",
    [
        "SubagentManagementExtension()",
        "SubagentManagementExtension(credential_track=CredentialTrack.PERSONAL)",
        "SubagentManagementExtension(credential_track=None)",
        "extensions.SubagentManagementExtension(**options)",
    ],
)
def test_the_guard_rejects_a_missing_or_literal_track(tmp_path: Path, call: str) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "site.py").write_text(f"{call}\n", encoding="utf-8")

    assert _extension_calls_missing_the_track(app_dir) == ["app/site.py:1"]


def test_the_guard_accepts_the_track_read_from_the_turn(tmp_path: Path) -> None:
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    (app_dir / "site.py").write_text(
        "SubagentManagementExtension(credential_track=agent_wrapper.credential_track)\n", encoding="utf-8"
    )

    assert _extension_calls_missing_the_track(app_dir) == []
