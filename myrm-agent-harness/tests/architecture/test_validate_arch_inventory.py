"""Tests for scripts/validate_arch_inventory.py."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_repo_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_repo_root))

import scripts.validate_arch_inventory as arch_module
from scripts.validate_arch_inventory import (
    DirReport,
    _format_reports,
    _listed_py_in_arch,
    _rel_to_repo,
    first_table_cell,
    is_inventory_file_cell,
    scan_directory,
    scan_tree,
)
from scripts.validate_arch_inventory import (
    main as arch_inventory_main,
)


@pytest.mark.architecture
def test_listed_py_ignores_prose_mentions(tmp_path: Path) -> None:
    arch = tmp_path / "_ARCH.md"
    arch.write_text(
        """# demo/

See server/stream_loop.py and stream_lane_factory.py for wiring.

| File | Role |
|------|------|
| `runner.py` | Core |
| `config.py` | Config |
""",
        encoding="utf-8",
    )
    assert _listed_py_in_arch(arch) == {"runner.py", "config.py"}


@pytest.mark.architecture
def test_listed_py_ignores_multi_file_comparison_cells(tmp_path: Path) -> None:
    arch = tmp_path / "_ARCH.md"
    arch.write_text(
        """| Allowed | Forbidden |
|---------|-----------|
| Root docs and package marker files (see note below) | Vendor packages |
| `_ARCH.md`, `SECURITY_WRAPPER_GUIDE.md`, `__init__.py` | Runtime/cache dirs |
""",
        encoding="utf-8",
    )
    assert _listed_py_in_arch(arch) == set()


@pytest.mark.architecture
def test_is_inventory_file_cell_rejects_prose_lists() -> None:
    assert not is_inventory_file_cell("_ARCH.md`, `SECURITY_WRAPPER_GUIDE.md`, `__init__.py")
    assert is_inventory_file_cell("dialog_manager.py")
    assert is_inventory_file_cell("__init__.py")
    assert not is_inventory_file_cell("api/hooks.py")


@pytest.mark.architecture
def test_scan_directory_detects_missing_and_extra(tmp_path: Path) -> None:
    (tmp_path / "listed.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "orphan.py").write_text("y = 2\n", encoding="utf-8")
    (tmp_path / "_ARCH.md").write_text(
        """| File | Role |
|------|------|
| `listed.py` | ok |
| `ghost.py` | stale |
""",
        encoding="utf-8",
    )
    report = scan_directory(tmp_path)
    assert report is not None
    assert report.missing_in_arch == ("orphan.py",)
    assert report.extra_in_arch == ("ghost.py",)


@pytest.mark.architecture
def test_middlewares_inventory_passes() -> None:
    middlewares = _repo_root / "src" / "myrm_agent_harness" / "agent" / "middlewares"
    report = scan_directory(middlewares)
    assert report is not None
    assert report.missing_in_arch == ()
    assert report.extra_in_arch == ()


@pytest.mark.architecture
def test_agent_arch_inventory_passes() -> None:
    import subprocess
    import sys

    agent_root = _repo_root / "src" / "myrm_agent_harness" / "agent"
    script = _repo_root / "scripts" / "validate_arch_inventory.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(agent_root)],
        cwd=_repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.architecture
def test_harness_arch_inventory_passes() -> None:
    import subprocess
    import sys

    harness_root = _repo_root / "src" / "myrm_agent_harness"
    script = _repo_root / "scripts" / "validate_arch_inventory.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(harness_root)],
        cwd=_repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.architecture
def test_harness_md_refs_pass() -> None:
    """Repo-root scan: table validation stays off, md refs must resolve (incl.
    top-level docs such as ARCHITECTURE.md and FRAMEWORK_DESIGN_PRINCIPLES.md)."""
    import subprocess
    import sys

    script = _repo_root / "scripts" / "validate_arch_inventory.py"
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(_repo_root), "--md-refs"],
        cwd=_repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


@pytest.mark.architecture
def test_server_md_refs_pass_in_monorepo() -> None:
    """Cross-repo scan: table validation is skipped, md refs must resolve."""
    import subprocess
    import sys

    script = _repo_root / "scripts" / "validate_arch_inventory.py"
    server_root = _repo_root.parent / "myrm-agent" / "myrm-agent-server"
    if not server_root.is_dir():
        pytest.skip("myrm-agent-server not checked out next to harness")
    result = subprocess.run(
        [sys.executable, str(script), "--root", str(server_root), "--md-refs"],
        cwd=_repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_first_table_cell_requires_closed_cell_pair() -> None:
    """A pipe-only fragment must not be treated as a table row."""
    assert first_table_cell("|dangling") is None
    assert first_table_cell("not a table row") is None


def test_scan_directory_missing_arch_returns_none(tmp_path: Path) -> None:
    """A directory without _ARCH.md produces no report instead of crashing."""
    (tmp_path / "mod.py").write_text("x = 1\n", encoding="utf-8")
    assert scan_directory(tmp_path) is None


def test_scan_tree_prunes_and_skips_irrelevant_dirs(tmp_path: Path) -> None:
    """Prune dirs and dirs without .py files never yield reports."""
    pruned = tmp_path / "__pycache__"
    pruned.mkdir()
    (pruned / "_ARCH.md").write_text("| File | Purpose |\n| --- | --- |\n", encoding="utf-8")
    (pruned / "cached.py").write_text("x = 1\n", encoding="utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()
    (empty / "_ARCH.md").write_text("| File | Purpose |\n| --- | --- |\n", encoding="utf-8")
    assert scan_tree(tmp_path) == []


def test_rel_to_repo_keeps_path_outside_repo(tmp_path: Path) -> None:
    """Paths outside the repository root stay absolute instead of '../'-walking."""
    outside = tmp_path / "outside" / "x.py"
    assert _rel_to_repo(outside) == outside


def test_format_reports_reports_missing_extra(tmp_path: Path) -> None:
    """Missing/extra .py entries are rendered as FAIL lines."""
    arch = tmp_path / "_ARCH.md"
    report = DirReport(
        directory=tmp_path,
        py_files=("real.py",),
        arch_path=arch,
        listed=("listed_ghost.py",),
        missing_in_arch=("real.py",),
        extra_in_arch=("listed_ghost.py",),
    )
    text = _format_reports([report], root_label="test")
    assert "FAIL" in text
    assert "real.py" in text
    assert "listed_ghost.py" in text


def test_main_missing_root_returns_2(tmp_path: Path) -> None:
    """A nonexistent --root is a usage error (exit 2)."""
    assert arch_inventory_main(["--root", str(tmp_path / "missing")]) == 2


def test_main_tables_outside_src_returns_2(tmp_path: Path) -> None:
    """Table scanning outside src/ (without --md-refs) is rejected."""
    assert arch_inventory_main(["--root", str(tmp_path)]) == 2


def test_main_clean_src_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A fully documented src/ subtree passes with exit 0."""
    repo = tmp_path / "repo"
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "_ARCH.md").write_text("| File | Purpose |\n| --- | --- |\n| mod.py | entry |\n", encoding="utf-8")
    (pkg / "mod.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_REPO_ROOT", repo)
    assert arch_inventory_main(["--root", str(pkg), "--json"]) == 0


def test_main_drifted_src_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A .py file missing from _ARCH.md fails with exit 1."""
    repo = tmp_path / "repo"
    pkg = repo / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "_ARCH.md").write_text("| File | Purpose |\n| --- | --- |\n| mod.py | entry |\n", encoding="utf-8")
    (pkg / "stale.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_REPO_ROOT", repo)
    assert arch_inventory_main(["--root", str(pkg)]) == 1


def test_format_reports_ok_line(tmp_path: Path) -> None:
    """A clean directory renders an OK line with its py-file count."""
    report = DirReport(
        directory=tmp_path,
        py_files=("real.py",),
        arch_path=tmp_path / "_ARCH.md",
        listed=frozenset({"real.py"}),
        missing_in_arch=(),
        extra_in_arch=(),
    )
    text = _format_reports([report], root_label="test")
    assert "OK" in text
    assert "PASS" in text


def test_main_md_refs_clean_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--md-refs on a repo root with resolvable refs passes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("`./mod.py` is referenced.\n", encoding="utf-8")
    (repo / "mod.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_REPO_ROOT", repo)
    assert arch_inventory_main(["--root", str(repo), "--md-refs"]) == 0


def test_main_md_refs_broken_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--md-refs with a dangling path reference fails."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("`./ghost.py` is referenced.\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_REPO_ROOT", repo)
    assert arch_inventory_main(["--root", str(repo), "--md-refs"]) == 1


def test_main_json_with_md_refs_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--json combined with --md-refs emits an md_refs payload and passes."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "guide.md").write_text("`./mod.py` is referenced.\n", encoding="utf-8")
    (repo / "mod.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_REPO_ROOT", repo)
    assert arch_inventory_main(["--root", str(repo), "--md-refs", "--json"]) == 0


def test_main_repo_refs_clean_returns_0(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--repo-refs passes when brand docs cite existing product sources."""
    workspace = tmp_path / "ws"
    brand = workspace / "myrm-agent-brand" / "docs"
    brand.mkdir(parents=True)
    (workspace / "myrm-agent" / "src").mkdir(parents=True)
    (workspace / "myrm-agent" / "src" / "real.py").write_text("x = 1\n", encoding="utf-8")
    (brand / "guide.mdx").write_text("See `myrm-agent/src/real.py`.\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(arch_module, "_BRAND_ROOT", workspace / "myrm-agent-brand")
    assert arch_inventory_main(["--root", str(workspace / "myrm-agent"), "--repo-refs"]) == 0


def test_main_repo_refs_broken_returns_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """--repo-refs fails when a cited product source no longer exists."""
    workspace = tmp_path / "ws"
    brand = workspace / "myrm-agent-brand" / "docs"
    brand.mkdir(parents=True)
    (workspace / "myrm-agent").mkdir(parents=True)
    (brand / "guide.mdx").write_text("See `myrm-agent/src/ghost.py`.\n", encoding="utf-8")
    monkeypatch.setattr(arch_module, "_WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(arch_module, "_BRAND_ROOT", workspace / "myrm-agent-brand")
    assert arch_inventory_main(["--root", str(workspace / "myrm-agent"), "--repo-refs"]) == 1


def test_main_repo_refs_skipped_without_brand_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A standalone harness clone has no brand repo, so the check skips instead of failing."""
    workspace = tmp_path / "ws"
    (workspace / "myrm-agent").mkdir(parents=True)
    monkeypatch.setattr(arch_module, "_WORKSPACE_ROOT", workspace)
    monkeypatch.setattr(arch_module, "_BRAND_ROOT", workspace / "myrm-agent-brand")
    assert arch_inventory_main(["--root", str(workspace / "myrm-agent"), "--repo-refs"]) == 0
