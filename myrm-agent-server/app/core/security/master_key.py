"""
[INPUT]
- keyring: OS 原生钥匙串（macOS Keychain / Linux secret-service / Windows Credential Manager）

[OUTPUT]
- VaultState: 主密钥解析状态
- VaultLockedError: 缺少主密钥时抛出，携带当前状态
- MasterKeyProvider: 为单机业务容器提供主密钥派生和内存保管服务

[POS]
安全金库密钥派生模块。主密钥只在内存中派生与保管，绝不落盘。OS 钥匙串读取固定在后台
守护线程执行，调用方只读缓存：恢复期间请求立即失败（不阻塞事件循环），钥匙串迟到返回的
密钥在用户尚未解锁时被采用。
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import threading
import time
from base64 import b64encode
from enum import StrEnum
from typing import Final

logger = logging.getLogger(__name__)

_KEYRING_SERVICE: Final = "myrm-agent-vault"
_KEYRING_ACCOUNT: Final = "master-key"

# A keyring read normally takes milliseconds. A longer wait means an OS authorization prompt is
# open or the keychain service is wedged; after this long the vault reports locked instead of
# "resolving", so callers get an actionable error rather than a pending state.
_KEYRING_TIMEOUT_SEC: Final = 10.0
# A failed read is retried only after this delay: each retry can raise another OS prompt.
_RETRY_AFTER_SEC: Final = 30.0
_RESOLUTION_THREAD_NAME: Final = "master-key-resolve"


class VaultState(StrEnum):
    """Lifecycle of the in-memory master key."""

    UNRESOLVED = "unresolved"
    RESOLVING = "resolving"
    READY = "ready"
    LOCKED = "locked"


class VaultLockedError(Exception):
    """Raised when the vault has no usable master key yet."""

    def __init__(self, message: str, *, state: VaultState = VaultState.LOCKED) -> None:
        super().__init__(message)
        self.state = state


def _keyring_available() -> bool:
    """Check if the keyring library is installed and functional."""
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def _load_from_keyring() -> str | None:
    """Read the master key from the OS keyring; a missing backend counts as "no key"."""
    try:
        import keyring
    except ImportError:
        return None
    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT) or None


def _save_to_keyring(key: str) -> bool:
    """Persist the master key in the OS keyring; a missing backend is a soft failure."""
    try:
        import keyring
    except ImportError:
        return False
    keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, key)
    return True


class MasterKeyProvider:
    """Provides the Master Key for the Agent Secret Vault.

    Priority chain (highest to lowest):
    1. MYRM_MASTER_KEY environment variable (SaaS / Control Plane injection)
    2. OS Keyring (macOS Keychain / Linux secret-service / Windows Credential Manager)
    3. Vault Password Unlock (In-Memory KDF)

    Strictly Zero-Disk: the master key is never written to disk in plain text. Keyring I/O runs on
    one daemon thread; every public entry point reads memory only, so a stuck keyring prompt can
    never block the event loop.
    """

    _master_key: str | None = None
    _state: VaultState = VaultState.UNRESOLVED
    _retry_after: float = 0.0
    _resolution_started_at: float = 0.0
    _resolution_thread: threading.Thread | None = None
    _lock = threading.Lock()

    @classmethod
    def get_master_key(cls) -> str:
        """Return the cached master key or raise immediately while resolution happens in the background."""
        if cls._master_key is not None:
            return cls._master_key

        static_key = cls._static_key()
        if static_key is not None:
            return static_key

        now = time.monotonic()
        with cls._lock:
            if cls._master_key is not None:
                return cls._master_key
            state = cls._effective_state(now)
            if state is VaultState.LOCKED and not cls._retry_due(now):
                raise VaultLockedError(
                    "Vault is locked. Provide MYRM_MASTER_KEY, configure OS keyring, or unlock via API.",
                    state=VaultState.LOCKED,
                )
            cls._start_resolution(now)
            raise VaultLockedError(
                "Vault is locked while the OS keyring prompt is pending. Approve it or unlock with a password.",
                state=VaultState.RESOLVING,
            )

    @classmethod
    async def ensure_master_key(cls, grace_sec: float = 2.0) -> str:
        """Wait up to ``grace_sec`` for the background keyring read, then raise with the current state."""
        deadline = time.monotonic() + grace_sec
        while True:
            try:
                return cls.get_master_key()
            except VaultLockedError as exc:
                if exc.state is VaultState.LOCKED or time.monotonic() >= deadline:
                    raise
                await asyncio.sleep(0.05)

    @classmethod
    def peek(cls) -> str | None:
        """Return the key only if it is already available; never starts a read or caches the result."""
        if cls._master_key is not None:
            return cls._master_key
        return os.getenv("MYRM_MASTER_KEY") or None

    @classmethod
    def prewarm(cls) -> None:
        """Start the background keyring read at startup without blocking the caller."""
        try:
            cls.get_master_key()
        except VaultLockedError:
            pass
        except Exception as exc:  # noqa: BLE001 - prewarm is best-effort; the first real use still raises
            logger.error("Master key prewarm failed: %s", exc)

    @classmethod
    def unlock_vault(cls, password: str, salt: bytes = b"myrm-vault-salt") -> str:
        """Unlock the vault with a user password and persist the derived key in the background."""
        derived_key = b64encode(hashlib.scrypt(password.encode("utf-8"), salt=salt, n=16384, r=8, p=1, dklen=32)).decode("utf-8")
        with cls._lock:
            cls._master_key = derived_key
            cls._state = VaultState.READY
            cls._retry_after = 0.0
        logger.info("Vault unlocked using provided password.")
        cls._persist_in_background(derived_key)
        return derived_key

    @classmethod
    def _static_key(cls) -> str | None:
        """Resolve the keys that need no I/O: the environment variable, then the sandbox guard."""
        env_key = os.getenv("MYRM_MASTER_KEY")
        if env_key:
            cls._master_key = env_key
            return env_key

        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        if get_deployment_capabilities().is_sandbox_instance:
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: MYRM_MASTER_KEY environment variable is missing. "
                "In SaaS deployment mode, the Control Plane MUST explicitly inject a master key to secure agent secrets."
            )
        return None

    @classmethod
    def _effective_state(cls, now: float) -> VaultState:
        """Report RESOLVING as LOCKED once the keyring has had its full window."""
        if cls._state is VaultState.RESOLVING and now - cls._resolution_started_at >= _KEYRING_TIMEOUT_SEC:
            logger.warning(
                "OS keyring did not answer within %.0fs (an authorization prompt may be open); vault reports locked.",
                _KEYRING_TIMEOUT_SEC,
            )
            cls._state = VaultState.LOCKED
            cls._retry_after = now + _RETRY_AFTER_SEC
        return cls._state

    @classmethod
    def _retry_due(cls, now: float) -> bool:
        """A retry is due only when the previous worker is gone and its cooldown elapsed."""
        worker = cls._resolution_thread
        if worker is not None and worker.is_alive():
            return False
        return now >= cls._retry_after

    @classmethod
    def _start_resolution(cls, now: float) -> None:
        """Start the single keyring reader; callers must hold ``_lock``."""
        worker = cls._resolution_thread
        if worker is not None and worker.is_alive():
            return
        cls._state = VaultState.RESOLVING
        cls._resolution_started_at = now
        cls._resolution_thread = threading.Thread(
            target=cls._read_keyring_worker,
            name=_RESOLUTION_THREAD_NAME,
            daemon=True,
        )
        cls._resolution_thread.start()

    @classmethod
    def _read_keyring_worker(cls) -> None:
        """Read the keyring once and publish the outcome; never overwrite an explicit unlock."""
        try:
            key = _load_from_keyring()
        except Exception as exc:  # noqa: BLE001 - a keyring backend failure must not kill the thread
            logger.debug("Keyring read failed (non-fatal): %s", exc)
            key = None

        with cls._lock:
            if cls._master_key is not None:
                # An explicit unlock won the race; the keyring answer must not replace it.
                cls._state = VaultState.READY
            elif key is None:
                cls._state = VaultState.LOCKED
                cls._retry_after = time.monotonic() + _RETRY_AFTER_SEC
            else:
                cls._master_key = key
                cls._state = VaultState.READY
                logger.info("Master Key loaded from OS keyring.")

    @classmethod
    def _persist_in_background(cls, key: str) -> None:
        """Persist to the OS keyring without making an unlock wait for a prompt."""
        if not _keyring_available():
            return

        def work() -> None:
            try:
                if _save_to_keyring(key):
                    logger.info("Derived Master Key securely saved to OS keyring for future use.")
            except Exception as exc:  # noqa: BLE001 - persistence is best-effort
                logger.warning("Failed to save the master key to the OS keyring: %s", exc)

        threading.Thread(target=work, name="master-key-persist", daemon=True).start()

    @classmethod
    def _reset_for_testing(cls) -> None:
        """Reset cached state. Only for unit tests."""
        with cls._lock:
            cls._master_key = None
            cls._state = VaultState.UNRESOLVED
            cls._retry_after = 0.0
            cls._resolution_started_at = 0.0
            cls._resolution_thread = None
