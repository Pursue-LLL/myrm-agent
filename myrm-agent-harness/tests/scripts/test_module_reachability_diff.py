"""Unit tests for scripts.module_reachability_diff and the ``--base`` mode of the reachability CLI.

Every case builds a real git repository under ``tmp_path`` holding a synthetic monorepo (the harness
package under ``harness/src``, its ``pyproject.toml`` beside it and a downstream tree under ``server/app``),
because the point of diff mode is the comparison against what git says the merge-base looked like.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))

from scripts import check_module_reachability as cli
from scripts.module_reachability_diff import (
    Analyse,
    BaseUnavailableError,
    DiffResult,
    Locate,
    diff_against,
    introduced_dead,
)
from scripts.module_reachability_engine import Report, Unit, analyze

_PACKAGE = "harness/src/pkg"
_PYPROJECT = "harness/pyproject.toml"
_SERVER = "server/app"
_SCAFFOLD = {
    _PYPROJECT: '[project]\nname = "pkg"\nversion = "0"\n',
    f"{_PACKAGE}/__init__.py": "",
    f"{_PACKAGE}/agent/__init__.py": "",
    f"{_PACKAGE}/agent/engine/__init__.py": "",
    f"{_PACKAGE}/agent/engine/used.py": "def run() -> None: ...\n",
    f"{_PACKAGE}/api/consumer.py": "from pkg.agent.engine.used import run\n\nrun()\n",
    f"{_SERVER}/main.py": "from app.svc.live import go\n\ngo()\n",
    f"{_SERVER}/svc/live.py": "def go() -> None: ...\n",
}
_ORPHAN = f"{_PACKAGE}/agent/engine/orphan.py"
_ORPHAN_KEY = "agent/engine/orphan"


def _git(repo: Path, *args: str) -> str:
    done = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout.strip()


def _write(repo: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        target = repo / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init", "-b", "main")
    _write(root, _SCAFFOLD)
    _commit(root, "base")
    return root


def _analyser(repo: Path) -> Analyse:
    def analyse(locate: Locate) -> Report:
        entry_points = cli.project_entry_points(locate(repo / _PYPROJECT))
        return analyze(locate(repo / _PACKAGE), entry_points=entry_points)

    return analyse


def _diff(repo: Path, rev: str = "main") -> tuple[Report, DiffResult]:
    analyse = _analyser(repo)
    head = analyse(lambda path: path)
    return head, diff_against(head, [repo / _PACKAGE, repo / _PYPROJECT], rev, analyse)


def test_unit_added_without_consumer_is_introduced(repo: Path) -> None:
    _git(repo, "switch", "-c", "feature")
    _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
    _commit(repo, "add unwired unit")

    _, result = _diff(repo)

    assert [unit.key for unit in result.introduced] == [_ORPHAN_KEY]
    assert result.preexisting == 0


def test_unit_already_dead_at_the_base_is_not_counted(repo: Path) -> None:
    _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
    _commit(repo, "dead on main")
    _git(repo, "switch", "-c", "feature")
    _write(repo, {f"{_PACKAGE}/agent/engine/used.py": "def run() -> None:\n    return None\n"})
    _commit(repo, "unrelated change")

    head, result = _diff(repo)

    assert [unit.key for unit in head.dead] == [_ORPHAN_KEY]
    assert result.introduced == ()
    assert result.preexisting == 1


def test_unit_orphaned_by_removing_its_consumer_is_introduced(repo: Path) -> None:
    _git(repo, "switch", "-c", "feature")
    (repo / _PACKAGE / "api/consumer.py").unlink()
    _commit(repo, "drop the only consumer")

    _, result = _diff(repo)

    assert [unit.key for unit in result.introduced] == ["agent/engine/used"]


def test_wiring_a_unit_that_was_dead_is_not_introduced(repo: Path) -> None:
    _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
    _commit(repo, "dead on main")
    _git(repo, "switch", "-c", "feature")
    _write(repo, {f"{_PACKAGE}/api/wire.py": "from pkg.agent.engine.orphan import lost\n\nlost()\n"})
    _commit(repo, "wire it")

    head, result = _diff(repo)

    assert head.dead == ()
    assert result.introduced == ()


def test_base_is_the_merge_base_not_the_tip_of_the_reference(repo: Path) -> None:
    fork_point = _git(repo, "rev-parse", "HEAD")
    _git(repo, "switch", "-c", "feature")
    _write(repo, {f"{_PACKAGE}/api/extra.py": "X = 1\n"})
    _commit(repo, "feature work")
    _git(repo, "switch", "main")
    _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
    _commit(repo, "main moves on")
    _git(repo, "switch", "feature")

    _, result = _diff(repo)

    assert result.base == fork_point
    assert result.introduced == ()


def test_entry_points_are_read_from_the_base_revision(repo: Path) -> None:
    _write(
        repo,
        {
            _PYPROJECT: '[project]\nname = "pkg"\nversion = "0"\n\n[project.scripts]\ncli = "pkg.agent.engine.cli:main"\n',
            f"{_PACKAGE}/agent/engine/cli.py": "def main() -> None: ...\n",
        },
    )
    _commit(repo, "console script on main")
    _git(repo, "switch", "-c", "feature")
    _write(repo, {_PYPROJECT: _SCAFFOLD[_PYPROJECT]})
    _commit(repo, "drop the console script")

    _, result = _diff(repo)

    assert [unit.key for unit in result.introduced] == ["agent/engine/cli"]


@pytest.mark.parametrize("rev", ["no-such-ref", "--version", ""])
def test_unresolvable_reference_fails_closed(repo: Path, rev: str) -> None:
    analyse = _analyser(repo)
    head = analyse(lambda path: path)

    with pytest.raises(BaseUnavailableError):
        diff_against(head, [repo / _PACKAGE, repo / _PYPROJECT], rev, analyse)


def test_directory_outside_git_fails_closed(tmp_path: Path) -> None:
    package = tmp_path / "pkg"
    _write(tmp_path, {"pkg/__init__.py": "", "pkg/agent/__init__.py": "", "pkg/agent/x.py": "X = 1\n"})
    head = analyze(package)

    with pytest.raises(BaseUnavailableError):
        diff_against(head, [package], "main", lambda locate: analyze(locate(package)))


def test_input_outside_the_repository_fails_closed(repo: Path, tmp_path: Path) -> None:
    outside = tmp_path / "elsewhere"
    _write(outside, {"x.py": "X = 1\n"})
    analyse = _analyser(repo)
    head = analyse(lambda path: path)

    with pytest.raises(BaseUnavailableError, match="outside"):
        diff_against(head, [repo / _PACKAGE, outside], "main", analyse)


def test_package_missing_at_the_base_fails_closed(repo: Path) -> None:
    _git(repo, "switch", "-c", "feature")
    _write(repo, {"other/__init__.py": "", "other/agent/__init__.py": "", "other/agent/x.py": "X = 1\n"})
    _commit(repo, "second package")
    other = repo / "other"
    head = analyze(other)

    with pytest.raises(BaseUnavailableError):
        diff_against(head, [other], "main", lambda locate: analyze(locate(other)))


def test_introduced_dead_matches_units_by_key() -> None:
    unit_a, unit_b = Unit("a/x", 3), Unit("a/y", 4)
    head = Report(units={}, dead=(unit_a, unit_b), server_only=(), files_scanned=0)
    base = Report(units={}, dead=(Unit("a/y", 99),), server_only=(), files_scanned=0)

    assert introduced_dead(head, base) == (unit_a,)


class TestCli:
    @pytest.fixture(autouse=True)
    def _point_cli_at_the_repo(self, repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(cli, "HARNESS_SRC", repo / _PACKAGE)
        monkeypatch.setattr(cli, "HARNESS_PYPROJECT", repo / _PYPROJECT)
        monkeypatch.setattr(cli, "SERVER_SRC", repo / _SERVER)

    def test_unwired_unit_added_by_the_change_exits_one(self, repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
        _git(repo, "switch", "-c", "feature")
        _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
        _commit(repo, "add unwired unit")

        assert cli.main(["--base", "main"]) == 1
        captured = capsys.readouterr()
        assert _ORPHAN_KEY in captured.err
        assert "left without a production consumer" in captured.err

    def test_unit_left_without_its_last_server_consumer_exits_one(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(
            repo,
            {
                f"{_PACKAGE}/agent/engine/served.py": "def serve() -> None: ...\n",
                f"{_SERVER}/main.py": "from app.svc.live import go\nfrom pkg.agent.engine.served import serve\n\ngo()\nserve()\n",
            },
        )
        _commit(repo, "the server serves a harness unit")
        _git(repo, "switch", "-c", "feature")
        _write(repo, {f"{_SERVER}/main.py": "from app.svc.live import go\n\ngo()\n"})
        _commit(repo, "the server stops using it")

        assert cli.main(["--base", "main"]) == 1
        assert "agent/engine/served" in capsys.readouterr().err

    def test_server_mode_names_the_server_unit_a_change_leaves_unwired(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _git(repo, "switch", "-c", "feature")
        _write(repo, {f"{_SERVER}/svc/orphan.py": "def lost() -> None: ...\n"})
        _commit(repo, "add an unwired server unit")

        assert cli.main(["--server", "--base", "main"]) == 1
        assert "svc/orphan" in capsys.readouterr().err

    def test_preexisting_dead_unit_does_not_fail_diff_mode_but_fails_absolute_mode(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
        _commit(repo, "dead on main")
        _git(repo, "switch", "-c", "feature")
        _write(repo, {f"{_PACKAGE}/api/extra.py": "X = 1\n"})
        _commit(repo, "unrelated change")

        assert cli.main(["--base", "main"]) == 0
        assert "1 unit(s) already dead there are not counted" in capsys.readouterr().out
        assert cli.main([]) == 1

    def test_unresolvable_base_exits_two(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert cli.main(["--base", "no-such-ref"]) == 2
        assert "cannot compare against --base no-such-ref" in capsys.readouterr().err

    def test_server_tree_outside_the_repository_exits_two(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        outside = tmp_path / "elsewhere" / "app"
        _write(outside, {"service.py": "VALUE = 1\n"})
        monkeypatch.setattr(cli, "SERVER_SRC", outside)

        assert cli.main(["--base", "main"]) == 2
        assert "outside" in capsys.readouterr().err

    def test_json_names_the_base_and_only_the_introduced_units(
        self, repo: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _write(repo, {_ORPHAN: "def lost() -> None: ...\n"})
        fork_point = _commit(repo, "dead on main")
        _git(repo, "switch", "-c", "feature")
        _write(repo, {f"{_PACKAGE}/agent/engine/fresh.py": "def new() -> None: ...\n"})
        _commit(repo, "add another unwired unit")

        assert cli.main(["--base", "main", "--json"]) == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["base"] == fork_point
        assert [item["unit"] for item in payload["dead"]] == ["agent/engine/fresh"]
