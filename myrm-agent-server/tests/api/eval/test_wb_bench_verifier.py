"""Unit tests for the WBBench verifier assertion builder (wb_bench.verifier).

Covers the missing-asset / malformed-declaration boundary paths of the native
grading protocol wiring: absent or invalid ``verifier.toml``, malformed
``[run]``/``[env]`` declarations, and family tasks that ship no grading
script. Happy-path wiring is covered by ``test_wb_bench_dataset.py``.
"""

from pathlib import Path

from app.core.eval.wb_bench.verifier import (
    _iter_verifier_env,
    _office_run_assertion,
    _read_verifier_toml,
    _test_suite_assertion_for,
    _verifier_run_command,
)


def _write_verifier_toml(task_dir: Path, content: str) -> Path:
    """Write ``tests/verifier.toml`` under a task dir and return its path."""
    tests_dir = task_dir / "tests"
    tests_dir.mkdir(parents=True, exist_ok=True)
    path = tests_dir / "verifier.toml"
    path.write_text(content)
    return path


def test_read_verifier_toml_missing_returns_none(tmp_path: Path) -> None:
    assert _read_verifier_toml(tmp_path) is None


def test_read_verifier_toml_invalid_toml_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, "family = 'unterminated\n")
    assert _read_verifier_toml(tmp_path) is None


def test_verifier_run_command_non_dict_run_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'family = "pytest_injected"\nrun = "oops"\n')
    verifier = _read_verifier_toml(tmp_path)
    assert verifier is not None
    assert _verifier_run_command(verifier, tmp_path / "tests") is None


def test_verifier_run_command_non_str_command_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'family = "pytest_injected"\n[run]\ncommand = 42\n')
    verifier = _read_verifier_toml(tmp_path)
    assert verifier is not None
    assert _verifier_run_command(verifier, tmp_path / "tests") is None


def test_office_assertion_without_command_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'schema_version = "workbuddy.office.verifier.v1"\n')
    verifier = _read_verifier_toml(tmp_path)
    assert verifier is not None
    assert _office_run_assertion(verifier, tmp_path / "tests", 600) is None


def test_iter_verifier_env_non_dict_returns_empty(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'family = "pytest_injected"\n[run]\ncommand = "x"\nenv = "nope"\n')
    verifier = _read_verifier_toml(tmp_path)
    assert verifier is not None
    assert _iter_verifier_env(verifier) == []


def test_script_verifier_without_script_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'family = "script_verifier"\n')
    assert _test_suite_assertion_for(tmp_path) is None


def test_pytest_injected_without_injected_dir_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'family = "pytest_injected"\n[run]\ncommand = "python -m pytest"\n')
    assert _test_suite_assertion_for(tmp_path) is None


def test_pytest_injected_falls_back_to_injected_root(tmp_path: Path) -> None:
    tests_dir = _write_verifier_toml(tmp_path, 'family = "pytest_injected"\n[run]\ncommand = "python -m pytest"\n').parent
    injected = tests_dir / "injected"
    injected.mkdir(parents=True)
    (injected / "test_app.py").write_text("def test_ok(): assert True\n")
    assertion = _test_suite_assertion_for(tmp_path)
    assert assertion is not None
    assert "cp -r" in assertion.target
    assert str(injected) in assertion.target


def test_repo_understanding_without_scorer_returns_none(tmp_path: Path) -> None:
    _write_verifier_toml(tmp_path, 'family = "repo_understanding"\n')
    assert _test_suite_assertion_for(tmp_path) is None
