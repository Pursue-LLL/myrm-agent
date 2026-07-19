"""Architecture test: remote-access E2EE modules live in a dedicated subpackage."""

from __future__ import annotations

from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_REMOTE_ACCESS_ROOT = _SERVER_ROOT / "app" / "remote_access"
_E2EE_PACKAGE = _REMOTE_ACCESS_ROOT / "e2ee"

_REQUIRED_MODULE_FILES = (
    "__init__.py",
    "_ARCH.md",
    "crypto.py",
    "keystore.py",
    "session.py",
    "response.py",
    "sse.py",
)

_FORBIDDEN_LEGACY_FLAT_FILES = (
    "e2ee_crypto.py",
    "e2ee_keystore.py",
    "e2ee_session.py",
    "e2ee_response.py",
    "e2ee_sse.py",
)


@pytest.mark.architecture
def test_e2ee_subpackage_layout() -> None:
    assert _E2EE_PACKAGE.is_dir(), (
        f"Missing {_E2EE_PACKAGE}. See app/remote_access/e2ee/_ARCH.md."
    )
    for filename in _REQUIRED_MODULE_FILES:
        path = _E2EE_PACKAGE / filename
        assert path.is_file(), f"Missing required e2ee module file: {path}"


@pytest.mark.architecture
@pytest.mark.parametrize("legacy_filename", _FORBIDDEN_LEGACY_FLAT_FILES)
def test_e2ee_legacy_flat_files_removed(legacy_filename: str) -> None:
    legacy_path = _REMOTE_ACCESS_ROOT / legacy_filename
    assert not legacy_path.exists(), (
        f"Legacy flat E2EE file must not reappear: {legacy_path}. "
        "Use app/remote_access/e2ee/ instead."
    )


@pytest.mark.architecture
def test_e2ee_public_exports() -> None:
    from app.remote_access.e2ee import (
        E2EESession,
        generate_keypair,
        get_e2ee_session_store,
        load_or_create_daemon_keypair,
    )

    assert E2EESession is not None
    assert generate_keypair is not None
    assert get_e2ee_session_store is not None
    assert load_or_create_daemon_keypair is not None
