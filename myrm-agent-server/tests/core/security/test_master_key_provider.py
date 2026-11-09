"""Tests for MasterKeyProvider: environment key, background keyring resolution, and vault unlock."""

import asyncio
import os
import threading
import time
from unittest.mock import patch

import pytest

from app.core.security import master_key
from app.core.security.master_key import (
    MasterKeyProvider,
    VaultLockedError,
    VaultState,
    _load_from_keyring,
    _save_to_keyring,
)

_STALL_SEC = 5.0
_PROMPT_SEC = 1.0


@pytest.fixture(autouse=True)
def _reset_provider():
    """Reset cached state and join leftover background workers before each test."""
    MasterKeyProvider._reset_for_testing()
    yield
    for worker in threading.enumerate():
        if worker.name in {"master-key-resolve", "master-key-persist"}:
            worker.join(_STALL_SEC + 1)
    MasterKeyProvider._reset_for_testing()


def _wait_for_key(timeout_sec: float = 2.0) -> str:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        try:
            return MasterKeyProvider.get_master_key()
        except VaultLockedError:
            time.sleep(0.01)
    raise AssertionError("master key was not resolved in time")


class TestEnvironmentVariable:
    def test_env_var_highest_priority(self) -> None:
        with patch.dict(os.environ, {"MYRM_MASTER_KEY": "env-key-123"}):
            assert MasterKeyProvider.get_master_key() == "env-key-123"

    def test_env_var_takes_precedence_over_keyring(self) -> None:
        with (
            patch.dict(os.environ, {"MYRM_MASTER_KEY": "env-key"}),
            patch("app.core.security.master_key._load_from_keyring", return_value="keyring-key") as loader,
        ):
            assert MasterKeyProvider.get_master_key() == "env-key"
        loader.assert_not_called()

    def test_cached_after_first_call(self) -> None:
        with patch.dict(os.environ, {"MYRM_MASTER_KEY": "cached-key"}):
            assert MasterKeyProvider.get_master_key() == "cached-key"
        assert MasterKeyProvider.get_master_key() == "cached-key"


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


class TestBackgroundResolution:
    def test_first_call_returns_before_keyring_answers(self) -> None:
        release = threading.Event()
        reads: list[str] = []

        def blocked_get(service: str, account: str) -> str:
            reads.append(account)
            release.wait(_STALL_SEC)
            return "keyring-master"

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):
            started = time.monotonic()
            with pytest.raises(VaultLockedError) as first:
                MasterKeyProvider.get_master_key()
            first_elapsed = time.monotonic() - started

            started = time.monotonic()
            with pytest.raises(VaultLockedError) as second:
                MasterKeyProvider.get_master_key()
            second_elapsed = time.monotonic() - started
            release.set()

            assert first.value.state is VaultState.RESOLVING
            assert second.value.state is VaultState.RESOLVING
            assert first_elapsed < _PROMPT_SEC
            assert second_elapsed < 0.1
            assert len(reads) == 1
            assert _wait_for_key() == "keyring-master"

    def test_late_answer_unlocks_the_vault(self) -> None:
        release = threading.Event()

        def blocked_get(service: str, account: str) -> str:
            release.wait(_STALL_SEC)
            return "late-key"

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            release.set()
            assert _wait_for_key() == "late-key"

    def test_failure_is_cached_until_retry_window_expires(self, monkeypatch: pytest.MonkeyPatch) -> None:
        reads: list[str] = []

        def missing_get(service: str, account: str) -> None:
            reads.append(account)
            return None

        monkeypatch.setattr(master_key, "_RETRY_AFTER_SEC", 0.3)
        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=missing_get),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            deadline = time.monotonic() + 2.0
            while MasterKeyProvider._state is not VaultState.LOCKED and time.monotonic() < deadline:
                time.sleep(0.01)
            assert MasterKeyProvider._state is VaultState.LOCKED

            with pytest.raises(VaultLockedError) as exc:
                MasterKeyProvider.get_master_key()
            assert exc.value.state is VaultState.LOCKED
            assert len(reads) == 1

            time.sleep(0.35)
            with pytest.raises(VaultLockedError) as retry:
                MasterKeyProvider.get_master_key()
            assert retry.value.state is VaultState.RESOLVING

            deadline = time.monotonic() + 2.0
            while len(reads) < 2 and time.monotonic() < deadline:
                time.sleep(0.01)
            assert len(reads) == 2

    def test_timeout_reports_locked_while_worker_is_alive(self, monkeypatch: pytest.MonkeyPatch) -> None:
        release = threading.Event()

        def blocked_get(service: str, account: str) -> None:
            release.wait(_STALL_SEC)
            return None

        monkeypatch.setattr(master_key, "_KEYRING_TIMEOUT_SEC", 0.1)
        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            time.sleep(0.15)
            with pytest.raises(VaultLockedError) as exc:
                MasterKeyProvider.get_master_key()
            release.set()

        assert exc.value.state is VaultState.LOCKED


class TestAsyncEnsure:
    def test_returns_immediately_when_resolved(self) -> None:
        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("app.core.security.master_key._load_from_keyring", return_value="async-key"),
        ):
            MasterKeyProvider.prewarm()

            async def run() -> str:
                return await MasterKeyProvider.ensure_master_key()

            assert asyncio.run(run()) == "async-key"

    def test_grace_expires_without_blocking_the_loop(self) -> None:
        release = threading.Event()
        gaps: list[float] = []

        def blocked_get(service: str, account: str) -> None:
            release.wait(_STALL_SEC)
            return None

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):

            async def run() -> None:
                async def ticker() -> None:
                    last = time.monotonic()
                    while True:
                        await asyncio.sleep(0.02)
                        now = time.monotonic()
                        gaps.append(now - last)
                        last = now

                task = asyncio.create_task(ticker())
                try:
                    with pytest.raises(VaultLockedError) as exc:
                        await MasterKeyProvider.ensure_master_key(grace_sec=0.2)
                finally:
                    task.cancel()
                assert exc.value.state is VaultState.RESOLVING

            asyncio.run(run())
            release.set()

        assert max(gaps) < 0.2


class TestVaultUnlock:
    def test_unlock_vault_stores_in_memory(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.core.security.master_key._keyring_available", return_value=False),
        ):
            derived_key = MasterKeyProvider.unlock_vault("my-secure-password")
            assert len(derived_key) > 20
            assert MasterKeyProvider.get_master_key() == derived_key

    def test_unlock_vault_saves_to_keyring_in_background(self) -> None:
        saved = threading.Event()

        def record_save(key: str) -> bool:
            saved.set()
            return True

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.core.security.master_key._keyring_available", return_value=True),
            patch("app.core.security.master_key._save_to_keyring", side_effect=record_save) as mock_save,
        ):
            derived_key = MasterKeyProvider.unlock_vault("my-secure-password")
            assert saved.wait(2.0)
            mock_save.assert_called_once_with(derived_key)

    def test_blocked_keyring_write_does_not_block_unlock(self) -> None:
        release = threading.Event()

        def blocked_set(service: str, account: str, key: str) -> None:
            release.wait(_STALL_SEC)

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("app.core.security.master_key._keyring_available", return_value=True),
            patch("keyring.set_password", side_effect=blocked_set),
        ):
            started = time.monotonic()
            derived = MasterKeyProvider.unlock_vault("my-secure-password")
            elapsed = time.monotonic() - started
            release.set()

        assert elapsed < _PROMPT_SEC
        assert MasterKeyProvider.get_master_key() == derived

    def test_late_keyring_answer_never_replaces_a_password_unlock(self) -> None:
        release = threading.Event()

        def blocked_get(service: str, account: str) -> str:
            release.wait(_STALL_SEC)
            return "late-key"

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
            patch("app.core.security.master_key._keyring_available", return_value=False),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()
            unlocked = MasterKeyProvider.unlock_vault("my-secure-password")
            release.set()
            time.sleep(0.2)

            assert MasterKeyProvider.get_master_key() == unlocked


class TestKeyringHelpers:
    def test_load_from_keyring_import_error(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            assert _load_from_keyring() is None

    def test_save_to_keyring_import_error(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            assert _save_to_keyring("test-key") is False

    def test_keyring_available_false_without_package(self) -> None:
        with patch.dict("sys.modules", {"keyring": None}):
            assert master_key._keyring_available() is False


class TestConcurrencyAndFailures:
    def test_concurrent_callers_share_one_reader(self) -> None:
        release = threading.Event()
        reads: list[str] = []

        def blocked_get(service: str, account: str) -> str:
            reads.append(account)
            release.wait(_STALL_SEC)
            return "shared-key"

        barrier = threading.Barrier(20)
        failures: list[VaultLockedError] = []

        def call() -> None:
            barrier.wait()
            try:
                MasterKeyProvider.get_master_key()
            except VaultLockedError as exc:
                failures.append(exc)

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):
            callers = [threading.Thread(target=call) for _ in range(20)]
            for caller in callers:
                caller.start()
            for caller in callers:
                caller.join(2.0)
            release.set()

            assert len(failures) == 20
            assert len(reads) == 1
            assert _wait_for_key() == "shared-key"

    def test_ensure_returns_a_late_key_within_the_grace_window(self) -> None:
        release = threading.Event()

        def blocked_get(service: str, account: str) -> str:
            release.wait(_STALL_SEC)
            return "late-key"

        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("keyring.get_password", side_effect=blocked_get),
        ):

            async def run() -> str:
                task = asyncio.create_task(MasterKeyProvider.ensure_master_key(grace_sec=2.0))
                await asyncio.sleep(0.1)
                release.set()
                return await task

            assert asyncio.run(run()) == "late-key"

    def test_prewarm_swallows_unexpected_failures(self, caplog: pytest.LogCaptureFixture) -> None:
        def boom() -> str:
            raise RuntimeError("sandbox key missing")

        with (
            patch.object(MasterKeyProvider, "get_master_key", side_effect=boom),
            caplog.at_level("ERROR"),
        ):
            MasterKeyProvider.prewarm()

        assert "Master key prewarm failed" in caplog.text

    def test_worker_survives_a_keyring_backend_crash(self) -> None:
        with (
            patch.dict(os.environ, {"DEPLOY_MODE": "local"}, clear=True),
            patch("app.core.security.master_key._load_from_keyring", side_effect=RuntimeError("backend down")),
        ):
            with pytest.raises(VaultLockedError):
                MasterKeyProvider.get_master_key()

            deadline = time.monotonic() + 2.0
            while MasterKeyProvider._state is not VaultState.LOCKED and time.monotonic() < deadline:
                time.sleep(0.01)

        assert MasterKeyProvider._state is VaultState.LOCKED

    def test_persist_failure_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        def failing_save(key: str) -> bool:
            raise RuntimeError("keychain denied")

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("app.core.security.master_key._keyring_available", return_value=True),
            patch("app.core.security.master_key._save_to_keyring", side_effect=failing_save),
            caplog.at_level("WARNING"),
        ):
            MasterKeyProvider.unlock_vault("my-secure-password")
            for worker in threading.enumerate():
                if worker.name == "master-key-persist":
                    worker.join(2.0)

        assert "Failed to save the master key" in caplog.text


class TestPeek:
    def test_peek_returns_none_without_starting_a_reader(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            assert MasterKeyProvider.peek() is None
        assert not any(worker.name == "master-key-resolve" for worker in threading.enumerate())

    def test_peek_returns_the_environment_key_without_caching(self) -> None:
        with patch.dict(os.environ, {"MYRM_MASTER_KEY": "peek-key"}):
            assert MasterKeyProvider.peek() == "peek-key"
        assert MasterKeyProvider._master_key is None

    def test_peek_prefers_an_unlocked_key(self) -> None:
        with (
            patch.dict(os.environ, {"MYRM_MASTER_KEY": "env-key"}),
            patch("app.core.security.master_key._keyring_available", return_value=False),
        ):
            unlocked = MasterKeyProvider.unlock_vault("my-secure-password")
            assert MasterKeyProvider.peek() == unlocked
