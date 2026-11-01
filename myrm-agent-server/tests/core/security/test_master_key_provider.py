"""Tests for MasterKeyProvider with Keyring and Vault integration."""

import os
import threading
import time
from unittest.mock import patch

import pytest

from app.core.security import master_key
from app.core.security.keyring_gate import KeyringGate
from app.core.security.master_key import (
    MasterKeyProvider,
    VaultLockedError,
    _load_from_keyring,
    _save_to_keyring,
)


@pytest.fixture(autouse=True)
def _reset_provider():
    """Reset cached state before each test."""
    MasterKeyProvider._reset_for_testing()
    yield
    MasterKeyProvider._reset_for_testing()


class TestEnvironmentVariable:
    def test_env_var_highest_priority(self) -> None:
        with patch.dict(os.environ, {"MYRM_MASTER_KEY": "env-key-123"}):
            key = MasterKeyProvider.get_master_key()
        assert key == "env-key-123"

    def test_env_var_takes_precedence_over_keyring(self) -> None:
        with (
            patch.dict(os.environ, {"MYRM_MASTER_KEY": "env-key"}),
            patch("app.core.security.master_key._load_from_keyring", return_value="keyring-key"),
        ):
            key = MasterKeyProvider.get_master_key()
        assert key == "env-key"

    def test_cached_after_first_call(self) -> None:
        with patch.dict(os.environ, {"MYRM_MASTER_KEY": "cached-key"}):
            key1 = MasterKeyProvider.get_master_key()
        # Even without env var, should return cached value
        key2 = MasterKeyProvider.get_master_key()
        assert key1 == key2 == "cached-key"


class TestSandboxFailFast:
    def test_sandbox_without_env_var_raises(self) -> None:
        from app.config.deploy_mode import get_deploy_mode
        from app.platform_utils.deployment_capabilities import _reset_capabilities_cache_for_testing

        get_deploy_mode.cache_clear()
        _reset_capabilities_cache_for_testing()
        with patch.dict(os.environ, {"DEPLOY_MODE": "sandbox"}, clear=False):
            os.environ.pop("MYRM_MASTER_KEY", None)
            get_deploy_mode.cache_clear()
            _reset_capabilities_cache_for_testing()
            try:
                with pytest.raises(RuntimeError, match="CRITICAL SECURITY ERROR"):
                    MasterKeyProvider.get_master_key()
            finally:
                get_deploy_mode.cache_clear()
                _reset_capabilities_cache_for_testing()


class TestKeyringIntegration:
    def test_load_from_keyring(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.core.security.master_key._load_from_keyring", return_value="keyring-master"),
        ):
            os.environ.pop("MYRM_MASTER_KEY", None)
            key = MasterKeyProvider.get_master_key()
        assert key == "keyring-master"

    def test_keyring_load_failure_raises_locked_error(self) -> None:
        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("app.core.security.master_key._load_from_keyring", return_value=None),
            patch("app.core.security.master_key._keyring_available", return_value=False),
        ):
            os.environ.pop("MYRM_MASTER_KEY", None)
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()


class TestVaultUnlock:
    def test_unlock_vault_stores_in_memory(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.core.security.master_key._keyring_available", return_value=False),
        ):
            derived_key = MasterKeyProvider.unlock_vault("my-secure-password")
            assert len(derived_key) > 20

            # Now get_master_key should succeed
            key = MasterKeyProvider.get_master_key()
            assert key == derived_key

    def test_unlock_vault_saves_to_keyring_if_available(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.core.security.master_key._keyring_available", return_value=True),
            patch("app.core.security.master_key._save_to_keyring", return_value=True) as mock_save,
        ):
            derived_key = MasterKeyProvider.unlock_vault("my-secure-password")

            mock_save.assert_called_once_with(derived_key)


class TestKeyringHelpers:
    def test_load_from_keyring_import_error(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            # When keyring import fails, should return None
            result = _load_from_keyring()
        assert result is None

    def test_save_to_keyring_import_error(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            result = _save_to_keyring("test-key")
        assert result is False


class TestStalledKeyring:
    """An OS keyring call that never answers (e.g. an unanswered macOS authorization prompt) must not freeze callers."""

    _LOCAL_ENV = {"DEPLOY_MODE": "local"}
    _PROMPT_SEC = 1.0
    _STALL_SEC = 5.0

    @pytest.fixture(autouse=True)
    def _short_gate(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(master_key, "_gate", KeyringGate(0.2), raising=False)
        yield
        # A released worker may still deliver its late key; let it finish before the provider state is reset.
        for worker in threading.enumerate():
            if worker.name == "keyring-call":
                worker.join(self._STALL_SEC + 1)

    def test_blocked_read_raises_locked_error_promptly_and_is_not_retried(self) -> None:
        release = threading.Event()
        reads: list[str] = []

        def blocked_get(service: str, account: str) -> str:
            reads.append(account)
            release.wait(self._STALL_SEC)
            return "late-key"

        with (
            patch.dict(os.environ, self._LOCAL_ENV, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):
            started = time.monotonic()
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            first = time.monotonic() - started

            started = time.monotonic()
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            second = time.monotonic() - started
            release.set()

        assert first < self._PROMPT_SEC
        assert second < 0.1
        assert len(reads) == 1

    def test_late_keyring_answer_unlocks_the_vault(self) -> None:
        release = threading.Event()
        reads: list[str] = []

        def blocked_get(service: str, account: str) -> str | None:
            reads.append(account)
            release.wait(self._STALL_SEC)
            # Only the stalled read carries the key, so the vault can only unlock by adopting its late answer.
            return "late-key" if len(reads) == 1 else None

        with (
            patch.dict(os.environ, self._LOCAL_ENV, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            release.set()

            deadline = time.monotonic() + 2.0
            key = None
            while key is None and time.monotonic() < deadline:
                try:
                    key = MasterKeyProvider.get_master_key()
                except VaultLockedError:
                    time.sleep(0.01)

        assert key == "late-key"

    def test_late_keyring_answer_never_replaces_a_password_unlock(self) -> None:
        release = threading.Event()

        def blocked_get(service: str, account: str) -> str:
            release.wait(self._STALL_SEC)
            return "late-key"

        with (
            patch.dict(os.environ, self._LOCAL_ENV, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
            patch("keyring.set_password"),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            unlocked = MasterKeyProvider.unlock_vault("my-secure-password")
            release.set()
            time.sleep(0.2)

            assert MasterKeyProvider.get_master_key() == unlocked

    def test_blocked_write_does_not_block_unlock(self) -> None:
        release = threading.Event()

        def blocked_set(service: str, account: str, key: str) -> None:
            release.wait(self._STALL_SEC)

        with (
            patch.dict(os.environ, self._LOCAL_ENV, clear=True),
            patch("keyring.set_password", side_effect=blocked_set),
        ):
            started = time.monotonic()
            derived = MasterKeyProvider.unlock_vault("my-secure-password")
            elapsed = time.monotonic() - started
            release.set()

        assert elapsed < self._PROMPT_SEC
        assert MasterKeyProvider.get_master_key() == derived
