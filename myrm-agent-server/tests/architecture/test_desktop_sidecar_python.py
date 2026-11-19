"""The macOS sidecar is frozen with a uv-managed Python, and a bundle that fell back to the python.org layout fails.

macOS scans every native file of a fresh install the first time it is loaded. The python.org build ships the standard
library's extension modules as dozens of separate files; a uv-managed build links nearly all of them into libpython, so
the first launch after an install or an update waits for far fewer files. uv takes a Python it finds on PATH before it
downloads its own, so the release workflow has to ask for the managed one, on macOS only, and `bundle_verify.py` reads the
finished bundle back so that a build which did not get it fails instead of shipping the slower layout.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import cast

import pytest
import yaml

from tests.support.desktop_release import ACTIONS, YamlMapping, release_steps, sidecar_module

# The conftest leaves test_desktop_* to desktop-contracts.yml; this mark also puts the file in the architecture gate.
pytestmark = pytest.mark.architecture

_SIDECAR_ACTION = "./.github/actions/build-sidecar"
_BUILD_JOBS = ("build-macos-arm", "build-windows", "build-linux")
_MANAGED_PYTHON_ENV = "UV_PYTHON_PREFERENCE=only-managed"
# What the python.org build of CPython 3.13 ships beside the interpreter, and what a uv-managed one does.
_PYTHON_ORG_EXTENSIONS = 59
_MANAGED_EXTENSIONS = 1


@pytest.fixture(scope="module")
def verify() -> ModuleType:
    return sidecar_module("bundle_verify")


def _sidecar_action() -> YamlMapping:
    return cast("YamlMapping", yaml.safe_load((ACTIONS / "build-sidecar/action.yml").read_text(encoding="utf-8")))


def _managed_python_input(job_id: str) -> object:
    calls = [step for step in release_steps(job_id) if step.get("uses") == _SIDECAR_ACTION]
    assert len(calls) == 1, f"{job_id} must build its sidecar once, through {_SIDECAR_ACTION}"
    return cast("YamlMapping", calls[0]["with"]).get("managed-python")


def test_only_the_macos_job_asks_the_sidecar_action_for_a_managed_python() -> None:
    # Windows and Linux have no first-launch scan of native files, so they keep the Python the runner provides.
    assert {job_id: _managed_python_input(job_id) for job_id in _BUILD_JOBS} == {
        "build-macos-arm": "true",
        "build-windows": None,
        "build-linux": None,
    }


def test_the_action_exports_the_managed_python_preference_only_when_asked_and_before_it_syncs_the_venv() -> None:
    action = _sidecar_action()
    steps = cast("list[YamlMapping]", cast("YamlMapping", action["runs"])["steps"])
    exporting = [index for index, step in enumerate(steps) if _MANAGED_PYTHON_ENV in str(step.get("run", ""))]
    sync = next(index for index, step in enumerate(steps) if "sync-server-venv.sh" in str(step.get("run", "")))

    assert len(exporting) == 1, "exactly one step may choose the interpreter the venv is created with"
    assert steps[exporting[0]]["if"] == "inputs.managed-python == 'true'"
    assert exporting[0] < sync, "uv picks the interpreter when it creates the venv"
    assert cast("YamlMapping", cast("YamlMapping", action["inputs"])["managed-python"])["default"] == "false"


def _bundle_shipping(tmp_path: Path, *, in_dynload: int, elsewhere: int = 0, layout: str = "python3.13/lib-dynload") -> Path:
    """A bundle directory whose `_internal` holds `in_dynload` standard-library extension modules under `layout`."""
    executable = tmp_path / "bundle" / "backend"
    internal = executable.parent / "_internal"
    (internal / layout).mkdir(parents=True)
    for index in range(in_dynload):
        (internal / layout / f"_stdlib{index}.cpython-313-darwin.so").write_text("", encoding="utf-8")
    (internal / layout / "notes.txt").write_text("", encoding="utf-8")
    (internal / "numpy" / "_core").mkdir(parents=True)
    for index in range(elsewhere):
        (internal / "numpy" / "_core" / f"_third_party{index}.cpython-313-darwin.so").write_text("", encoding="utf-8")
    return executable


def _problems(verify: ModuleType, monkeypatch: pytest.MonkeyPatch, executable: Path, platform: str) -> list[str]:
    """What the verifier reports for a bundle that holds every module, script and data file the inventory asks for."""
    monkeypatch.setattr(verify, "bundled_module_names", lambda _executable: set())
    monkeypatch.setattr(verify, "first_party_modules", lambda *_args: {})
    monkeypatch.setattr(verify, "domain_tool_scripts", lambda _harness: [])
    monkeypatch.setattr(verify, "harness_data_files", lambda _harness: [])
    return verify.bundle_problems(executable, Path("app"), Path("harness"), platform=platform)


def test_the_verifier_accepts_the_layout_of_a_uv_managed_python_on_macos(
    verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _bundle_shipping(tmp_path, in_dynload=_MANAGED_EXTENSIONS)

    assert _problems(verify, monkeypatch, executable, "darwin") == []


def test_the_verifier_accepts_a_bundle_at_the_limit_and_names_one_past_it(
    verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    at_limit = _bundle_shipping(tmp_path / "at", in_dynload=verify.MAX_STDLIB_EXTENSION_FILES)
    past_limit = _bundle_shipping(tmp_path / "past", in_dynload=verify.MAX_STDLIB_EXTENSION_FILES + 1)

    assert _problems(verify, monkeypatch, at_limit, "darwin") == []
    assert len(_problems(verify, monkeypatch, past_limit, "darwin")) == 1


def test_the_limit_separates_the_two_layouts_with_room_to_spare(verify: ModuleType) -> None:
    assert _MANAGED_EXTENSIONS < verify.MAX_STDLIB_EXTENSION_FILES < _PYTHON_ORG_EXTENSIONS


def test_the_verifier_rejects_the_layout_of_the_python_org_build_on_macos_and_says_how_to_fix_it(
    verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = _bundle_shipping(tmp_path, in_dynload=_PYTHON_ORG_EXTENSIONS)

    problems = _problems(verify, monkeypatch, executable, "darwin")

    assert len(problems) == 1
    assert f"{_PYTHON_ORG_EXTENSIONS} standard-library extension modules" in problems[0]
    assert _MANAGED_PYTHON_ENV in problems[0]


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_the_verifier_does_not_hold_the_other_platforms_to_the_macos_layout(
    verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    executable = _bundle_shipping(tmp_path, in_dynload=_PYTHON_ORG_EXTENSIONS)

    assert _problems(verify, monkeypatch, executable, platform) == []


@pytest.mark.parametrize("layout", ["python3.13/lib-dynload", "lib-dynload"])
def test_the_count_follows_lib_dynload_wherever_the_bundle_puts_it_and_ignores_other_extension_modules(
    verify: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, layout: str
) -> None:
    # Third-party extension modules (numpy, PIL, ...) are the packages' own files and not what the check is about.
    leaner = _bundle_shipping(tmp_path / "leaner", in_dynload=_MANAGED_EXTENSIONS, elsewhere=200, layout=layout)
    fatter = _bundle_shipping(tmp_path / "fatter", in_dynload=_PYTHON_ORG_EXTENSIONS, layout=layout)

    assert _problems(verify, monkeypatch, leaner, "darwin") == []
    assert len(_problems(verify, monkeypatch, fatter, "darwin")) == 1


def test_the_build_checks_the_platform_it_runs_on_unless_told_otherwise(verify: ModuleType) -> None:
    assert inspect.signature(verify.bundle_problems).parameters["platform"].default == sys.platform
