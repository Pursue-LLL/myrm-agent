"""Architecture test: server pyproject.toml must match uv.lock requires-dist declarations."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

from tests.architecture.test_uv_lock_harness_registry import _harness_sync_lock_ready_on_pypi

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_PYPROJECT = _SERVER_ROOT / "pyproject.toml"
_LOCK_PATH = _SERVER_ROOT / "uv.lock"

_FORBIDDEN_REQUIRES_DIST = (
    "aiofiles",
    "advanced-tools",
    'httpx", extras = ["socks"]',
    "httpx\", extras = ['socks']",
)


def _main_dependency_names() -> set[str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    names: set[str] = set()
    for dep in data["project"]["dependencies"]:
        base = dep.split(";")[0].strip()
        name = re.split(r"[<>=!\[]", base, maxsplit=1)[0].strip()
        names.add(name.lower().replace("_", "-"))
    return names


def _lock_requires_dist_block() -> str:
    text = _LOCK_PATH.read_text(encoding="utf-8")
    marker = 'name = "myrmagentserver"'
    start = text.find(marker)
    assert start != -1, "myrmagentserver package not found in uv.lock"
    section = text[start:]
    req_start = section.find("requires-dist = [")
    assert req_start != -1, "requires-dist block missing for myrmagentserver"
    req_end = section.find("]\nprovides-extras", req_start)
    assert req_end != -1, "requires-dist block end not found"
    return section[req_start:req_end]


def _optional_extra_names() -> set[str]:
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    return set(data["project"].get("optional-dependencies", {}).keys())


@pytest.mark.architecture
def test_pyproject_main_deps_have_evidence_packages() -> None:
    """Sanity: core declared deps include harness and httpx."""
    names = _main_dependency_names()
    assert "myrm-agent-harness" in names
    assert "httpx" in names
    assert "tenacity" in names
    assert "filelock" in names
    assert "aiofiles" not in names


@pytest.mark.architecture
def test_lock_forbids_removed_declarations() -> None:
    """Regression: dead deps and retired extras must not reappear in lock metadata."""
    block = _lock_requires_dist_block()
    for forbidden in _FORBIDDEN_REQUIRES_DIST:
        assert forbidden not in block, f"uv.lock still lists forbidden declaration: {forbidden}"


@pytest.mark.architecture
def test_lock_provides_extras_match_pyproject() -> None:
    """optional-dependencies in pyproject must match provides-extras in lock."""
    text = _LOCK_PATH.read_text(encoding="utf-8")
    match = re.search(
        r'name = "myrmagentserver"[\s\S]*?provides-extras = \[(.*?)\]',
        text,
    )
    assert match is not None
    lock_extras = {e.strip().strip('"') for e in match.group(1).split(",") if e.strip()}
    assert lock_extras == _optional_extra_names()


@pytest.mark.architecture
@pytest.mark.skipif(
    _harness_sync_lock_ready_on_pypi(),
    reason="PyPI harness pin active; editable monorepo path is not committed in uv.lock",
)
def test_lock_harness_editable_monorepo_path() -> None:
    """Monorepo dev: harness editable path must resolve from myrm-agent-server/."""
    text = _LOCK_PATH.read_text(encoding="utf-8")
    assert 'editable = "../../myrm-agent-harness"' in text
    assert 'editable = "../myrm-agent-harness"' not in text


@pytest.mark.architecture
def test_lock_includes_matrix_extra_markers() -> None:
    """Matrix optional extra must be present in lock metadata."""
    block = _lock_requires_dist_block()
    assert "extra == 'matrix'" in block or 'extra == "matrix"' in block
    assert "aiohttp-socks" in block
    assert "mautrix" in block
