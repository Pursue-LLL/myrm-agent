"""Unit tests for scripts.check_module_reachability (CLI wiring, exit codes, loud degradation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts import check_module_reachability as cli


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    return root


@pytest.fixture
def trees(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    harness = _write(
        tmp_path / "pkg",
        {
            "__init__.py": "",
            "agent/__init__.py": "",
            "agent/engine/__init__.py": "",
            "agent/engine/used.py": "def run() -> None: ...\n",
            "api/consumer.py": "from pkg.agent.engine.used import run\n\nrun()\n",
        },
    )
    server = _write(tmp_path / "server", {"service.py": "VALUE = 1\n"})
    monkeypatch.setattr(cli, "HARNESS_SRC", harness)
    monkeypatch.setattr(cli, "HARNESS_PYPROJECT", tmp_path / "pyproject.toml")
    monkeypatch.setattr(cli, "SERVER_SRC", server)
    return harness, server


def test_clean_tree_exits_zero(trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main([]) == 0
    assert "OK: every unit has a production consumer" in capsys.readouterr().out


def test_dead_unit_exits_one_and_names_it(trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    harness, _ = trees
    _write(harness, {"agent/engine/orphan.py": "def lost() -> None: ...\n"})
    assert cli.main([]) == 1
    err = capsys.readouterr().err
    assert "agent/engine/orphan" in err
    assert "no allowlist" in err


def test_json_output_lists_dead_units(trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    harness, _ = trees
    _write(harness, {"agent/engine/orphan.py": "def lost() -> None: ...\n"})
    assert cli.main(["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert [item["unit"] for item in payload["dead"]] == ["agent/engine/orphan"]
    assert payload["units"] == 2


def test_scan_without_units_fails_instead_of_passing_silently(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "HARNESS_SRC", _write(tmp_path / "pkg", {"api/only.py": "X = 1\n"}))
    monkeypatch.setattr(cli, "SERVER_SRC", _write(tmp_path / "server", {"service.py": "X = 1\n"}))
    assert cli.main([]) == 2
    assert "nothing was scanned" in capsys.readouterr().err


def test_missing_server_tree_is_reported_not_green(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "SERVER_SRC", tmp_path / "absent")
    assert cli.main([]) == 0
    assert "NOT EVALUATED" in capsys.readouterr().out


def test_require_server_fails_when_the_server_tree_is_missing(
    trees: tuple[Path, Path], monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(cli, "SERVER_SRC", tmp_path / "absent")
    assert cli.main(["--require-server"]) == 3
    assert "server tree not found" in capsys.readouterr().err


def test_dead_server_unit_does_not_keep_a_harness_unit_alive(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    harness, server = trees
    _write(harness, {"agent/engine/ghost.py": "def haunt() -> None: ...\n"})
    _write(server, {"svc/dead.py": "from pkg.agent.engine.ghost import haunt\n\nhaunt()\n"})
    assert cli.main([]) == 1
    assert "agent/engine/ghost" in capsys.readouterr().err


def test_harness_mode_honours_root_dirs(trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    harness, _ = trees
    _write(
        harness,
        {
            "toolkits/browser/domain_skills/builtin/skill.py": "def run() -> None: ...\n",
            "toolkits/browser/domain_skills/orphan.py": "def lost() -> None: ...\n",
            "toolkits/browser/orphan.py": "def lost() -> None: ...\n",
            "toolkits/orphan.py": "def lost() -> None: ...\n",
        },
    )
    assert cli.main(["--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert sorted(item["unit"] for item in payload["dead"]) == [
        "toolkits/browser/domain_skills/orphan",
        "toolkits/browser/orphan",
        "toolkits/orphan",
    ]


def test_server_mode_audits_server_units_and_honours_root_dirs(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    _, server = trees
    _write(
        server,
        {
            "main.py": "from server.svc.live import go\n\ngo()\n",
            "svc/live.py": "def go() -> None: ...\n",
            "svc/orphan.py": "def lost() -> None: ...\n",
            "channels/providers/slack.py": "def load() -> None: ...\n",
            "channels/helpers/orphan.py": "def lost() -> None: ...\n",
            "startup/runner.py": "def run() -> None: ...\n",
        },
    )
    assert cli.main(["--server", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["tree"] == "server"
    assert sorted(item["unit"] for item in payload["dead"]) == ["channels/helpers/orphan", "svc/orphan"]


def test_server_root_option_overrides_the_default_tree(
    trees: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    other = _write(tmp_path / "other", {"svc/orphan.py": "def lost() -> None: ...\n"})
    assert cli.main(["--server", "--server-root", str(other)]) == 1
    assert "svc/orphan" in capsys.readouterr().err


def test_server_mode_fails_when_the_server_tree_is_missing(
    trees: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(["--server", "--server-root", str(tmp_path / "absent")]) == 3
    assert "server tree not found" in capsys.readouterr().err


def test_console_script_target_is_a_root(trees: tuple[Path, Path], tmp_path: Path) -> None:
    harness, _ = trees
    _write(harness, {"agent/engine/tool.py": "def main() -> None: ...\n"})
    assert cli.main([]) == 1
    (tmp_path / "pyproject.toml").write_text(
        '[project.scripts]\ntool = "pkg.agent.engine.tool:main"\n', encoding="utf-8"
    )
    assert cli.main([]) == 0


def test_project_entry_points_reads_console_scripts(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text('[project.scripts]\ntool = "pkg.agent.engine.cli:main"\n', encoding="utf-8")
    assert cli.project_entry_points(pyproject) == ("pkg.agent.engine.cli:main",)
    assert cli.project_entry_points(tmp_path / "missing.toml") == ()


_PENDING_MODULE = '''"""A unit waiting for its caller.

[POS]
Something implemented and tested, not wired yet.

[PENDING] No caller yet: the surface that will use it ships with the next feature.
"""


def run() -> None: ...
'''


def test_a_pending_unit_is_reported_and_does_not_fail_the_gate(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    harness, _ = trees
    _write(harness, {"agent/engine/waiting.py": _PENDING_MODULE})

    assert cli.main([]) == 0

    out = capsys.readouterr().out
    assert "1 unit(s) declared [PENDING]" in out
    assert "agent/engine/waiting" in out
    assert "the surface that will use it ships with the next feature" in out


def test_pending_units_appear_in_json_with_their_reason(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    harness, _ = trees
    _write(harness, {"agent/engine/waiting.py": _PENDING_MODULE})

    assert cli.main(["--json"]) == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["dead"] == []
    assert [item["unit"] for item in payload["pending"]] == ["agent/engine/waiting"]
    assert payload["pending"][0]["reason"].startswith("No caller yet")


def test_a_pending_unit_that_gained_a_consumer_fails_until_the_note_is_dropped(
    trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]
) -> None:
    harness, _ = trees
    _write(
        harness,
        {
            "agent/engine/waiting.py": _PENDING_MODULE,
            "api/uses_waiting.py": "from pkg.agent.engine.waiting import run\n\nrun()\n",
        },
    )

    assert cli.main([]) == 1

    err = capsys.readouterr().err
    assert "still say [PENDING] but already have a production consumer" in err
    assert "agent/engine/waiting" in err


def test_a_pending_note_spans_continuation_lines(trees: tuple[Path, Path], capsys: pytest.CaptureFixture[str]) -> None:
    harness, _ = trees
    _write(
        harness,
        {
            "agent/engine/waiting.py": (
                '"""Waiting.\n\n[POS]\nPlaceholder.\n\n'
                '[PENDING] First half of the reason,\nand the second half.\n"""\n\n\ndef run() -> None: ...\n'
            )
        },
    )

    assert cli.main(["--json"]) == 0

    reason = json.loads(capsys.readouterr().out)["pending"][0]["reason"]
    assert reason == "First half of the reason, and the second half."
