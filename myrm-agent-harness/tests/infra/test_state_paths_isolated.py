"""A process given its own state root keeps every default state path inside it.

The home directory is the other profile's data. These tests point ``HOME`` at a directory standing in for it,
give the process a separate ``MYRM_DATA_DIR`` and resolve each default state path: all must land in the root, and
nothing may be created in the home directory. ``tests/architecture/test_state_paths_follow_data_dir.py`` (server)
guards the source text; this runs the code.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest


def _domain_metrics() -> Path:
    from myrm_agent_harness.toolkits.web_fetch.router.domain_metrics import DomainMetricsManager

    return DomainMetricsManager._resolve_storage_path(None)


def _site_experience() -> Path:
    from myrm_agent_harness.toolkits.web_fetch.router.site_experience import SiteExperienceStore

    return SiteExperienceStore._resolve_storage_path(None)


def _domain_skills() -> Path:
    from myrm_agent_harness.toolkits.browser.domain_skills.store import DomainSkillStore

    return DomainSkillStore._resolve_user_dir(None)


def _shadow_git_snapshots() -> Path:
    from myrm_agent_harness.agent.file_snapshot.shadow_git_store import _default_store_path

    return _default_store_path()


def _snapshot_factory() -> Path:
    from myrm_agent_harness.agent.file_snapshot.factory import _default_store_base

    return _default_store_base()


def _local_snapshots() -> Path:
    from myrm_agent_harness.agent.file_snapshot.local_store import _default_local_snapshot_path

    return _default_local_snapshot_path()


def _skill_config_version() -> Path:
    from myrm_agent_harness.backends.skills.config_version import _version_path

    return _version_path()


def _shared_venv() -> Path:
    from myrm_agent_harness.toolkits.code_execution.executors.common.venv_manager import _get_default_venv_path

    return _get_default_venv_path()


def _storage_root() -> Path:
    from myrm_agent_harness.toolkits.storage.config import _get_default_storage_path

    return Path(_get_default_storage_path())


def _engine_affinity() -> Path:
    from myrm_agent_harness.toolkits.browser.pool.engine_affinity import _store_path

    return Path(_store_path())


def _estop_state() -> Path:
    from myrm_agent_harness.agent.security.guards.estop import EStopGuard

    return EStopGuard._default_path()


def _memory_blobs() -> Path:
    from myrm_agent_harness.toolkits.memory.compression import _blob_root

    return _blob_root(None)


def _memory_config_blobs() -> Path:
    from myrm_agent_harness.toolkits.memory.config import MemoryConfig

    return Path(MemoryConfig(embedding_model="test").blob_storage_path)


_DEFAULT_STATE_PATHS: dict[str, Callable[[], Path]] = {
    "domain_metrics": _domain_metrics,
    "site_experience": _site_experience,
    "domain_skills": _domain_skills,
    "shadow_git_snapshots": _shadow_git_snapshots,
    "snapshot_factory": _snapshot_factory,
    "local_snapshots": _local_snapshots,
    "skill_config_version": _skill_config_version,
    "shared_venv": _shared_venv,
    "storage_root": _storage_root,
    "engine_affinity": _engine_affinity,
    "estop_state": _estop_state,
    "memory_blobs": _memory_blobs,
    "memory_config_blobs": _memory_config_blobs,
}


@pytest.fixture
def profiles(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    """``(home, root)``: a home directory belonging to someone else and this process's own state root."""
    home = tmp_path / "home"
    root = tmp_path / "root"
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("MYRM_DATA_DIR", str(root))
    return home, root


@pytest.mark.parametrize("name", sorted(_DEFAULT_STATE_PATHS))
def test_a_default_state_path_lies_inside_the_state_root(name: str, profiles: tuple[Path, Path]) -> None:
    _home, root = profiles

    resolved = _DEFAULT_STATE_PATHS[name]()

    assert resolved.resolve().is_relative_to(root.resolve()), f"{name} resolved to {resolved}, outside {root}"


def test_resolving_the_default_state_paths_creates_nothing_in_the_home_directory(profiles: tuple[Path, Path]) -> None:
    home, _root = profiles

    for resolve in _DEFAULT_STATE_PATHS.values():
        resolve()

    assert not home.exists()
