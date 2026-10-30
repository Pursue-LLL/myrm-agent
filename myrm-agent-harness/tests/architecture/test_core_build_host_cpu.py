"""Architecture gate: a core build refuses a platform key whose CPU is not the CPU of the build host."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO_ROOT))

from harness_packaging.platforms import platform_spec_for_key
from scripts import build_core


def _host(monkeypatch: pytest.MonkeyPatch, platform_key: str) -> None:
    monkeypatch.setattr(build_core, "get_current_platform", lambda: platform_spec_for_key(platform_key))


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("host", "requested"),
    [
        ("darwin-arm64", "darwin-x64"),
        ("darwin-x64", "darwin-arm64"),
        ("win32-x64", "win32-arm64"),
        ("linux-x64", "linux-arm64-musl"),
    ],
)
def test_a_platform_key_is_not_compiled_on_a_host_with_another_cpu(
    monkeypatch: pytest.MonkeyPatch, host: str, requested: str
) -> None:
    """Nuitka would exit 0 and leave host code under the wrong platform name, so the build stops before compiling."""
    _host(monkeypatch, host)
    monkeypatch.setattr(build_core, "_require_nuitka", lambda: None)

    with pytest.raises(SystemExit, match=f"Cannot build {requested} on this host"):
        build_core.compile_core(platform_spec_for_key(requested))


@pytest.mark.architecture
@pytest.mark.parametrize(
    ("host", "requested"),
    [("darwin-arm64", "darwin-arm64"), ("linux-x64", "linux-x64-musl"), ("win32-arm64", "win32-arm64")],
)
def test_a_platform_key_with_the_cpu_of_the_host_is_accepted(
    monkeypatch: pytest.MonkeyPatch, host: str, requested: str
) -> None:
    _host(monkeypatch, host)

    build_core._require_host_cpu(platform_spec_for_key(requested))
