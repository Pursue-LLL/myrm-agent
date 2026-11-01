"""
[INPUT]
keyring_gate::KeyringGate (POS: 限时执行 OS 钥匙串调用)

[OUTPUT]
VaultLockedError: 当缺少主密钥且金库锁定且无法获取时抛出
MasterKeyProvider: 为单机业务容器提供主密钥派生和内存保管服务

[POS]
安全金库密钥派生模块。提供零落盘的主密钥内存派生与验证服务，保护凭证安全；OS 钥匙串读写限时 10 秒，超时按金库锁定处理。
"""

import hashlib
import logging
import os
import threading
from base64 import b64encode

from .keyring_gate import KeyringGate

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "myrm-agent-vault"
_KEYRING_ACCOUNT = "master-key"

# A keyring read normally takes milliseconds. A longer wait means an OS authorization prompt is open or the keychain
# service is wedged, and every caller (including server startup) would freeze behind it, so give up after this long.
_KEYRING_TIMEOUT_SEC = 10.0
_gate = KeyringGate(_KEYRING_TIMEOUT_SEC)


class VaultLockedError(Exception):
    """Raised when the master key is not available and the vault is locked."""

    pass


def _keyring_available() -> bool:
    """Check if the keyring library is installed and functional."""
    try:
        import keyring  # noqa: F401

        return True
    except ImportError:
        return False


def _read_keyring() -> str | None:
    import keyring

    return keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT) or None


def _write_keyring(key: str) -> bool:
    import keyring

    keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, key)
    return True


def _load_from_keyring() -> str | None:
    """Load the master key from the OS keyring; None when absent, failed, or the keyring did not answer in time."""
    return _gate.run(_read_keyring, MasterKeyProvider._adopt_late_key)


def _save_to_keyring(key: str) -> bool:
    """Save the master key to the OS keyring; False when it failed or the keyring did not answer in time."""
    return _gate.run(lambda: _write_keyring(key), lambda _saved: None) is True


class MasterKeyProvider:
    """Provides the Master Key for the Agent Secret Vault.

    Priority chain (highest to lowest):
    1. MYRM_MASTER_KEY environment variable (SaaS / Control Plane injection)
    2. OS Keyring (macOS Keychain / Linux secret-service / Windows Credential Manager)
    3. Vault Password Unlock (In-Memory KDF)

    Strictly Zero-Disk: We NEVER write the master key to a plain text file on disk.
    If the key is not in the environment and keyring is unavailable, a VaultLockedError is raised.
    The frontend must then prompt the user to unlock the vault.
    """

    _master_key: str | None = None
    _adopt_lock = threading.Lock()

    @classmethod
    def get_master_key(cls) -> str:
        """Get the master key, initializing it if necessary."""
        if cls._master_key is not None:
            return cls._master_key

        cls._master_key = cls._resolve_key()
        return cls._master_key

    @classmethod
    def _resolve_key(cls) -> str:
        """Walk the priority chain to find the master key."""
        # 1. Environment variable (highest priority — SaaS / Control Plane)
        env_key = os.getenv("MYRM_MASTER_KEY")
        if env_key:
            logger.info("Master Key loaded from MYRM_MASTER_KEY environment variable.")
            return env_key

        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        if get_deployment_capabilities().is_sandbox_instance:
            raise RuntimeError(
                "CRITICAL SECURITY ERROR: MYRM_MASTER_KEY environment variable is missing. "
                "In SaaS deployment mode, the Control Plane MUST explicitly inject a master key to secure agent secrets."
            )

        # 2. Try OS Keyring (for Local / Tauri desktop modes)
        keyring_key = _load_from_keyring()
        if keyring_key:
            logger.info("Master Key loaded from OS keyring.")
            return keyring_key

        # 3. Vault is locked.
        # Zero-Disk Architecture: We absolutely refuse to write a fallback plaintext file to disk.
        logger.warning("Master Key not found in environment or OS keyring. Vault is locked.")
        raise VaultLockedError("Vault is locked. Provide MYRM_MASTER_KEY, configure OS keyring, or unlock via API.")

    @classmethod
    def _adopt_late_key(cls, key: str) -> None:
        """Keep a key the OS keyring delivered after its caller gave up, unless the vault was unlocked meanwhile."""
        with cls._adopt_lock:
            if cls._master_key is None:
                cls._master_key = key
                logger.info("Master Key loaded from OS keyring after a delayed answer.")

    @classmethod
    def unlock_vault(cls, password: str, salt: bytes = b"myrm-vault-salt") -> str:
        """Unlock the vault using a user-provided password.

        Derives a 32-byte key using scrypt and stores it in memory.
        If keyring is available, it will securely persist the derived key.
        """
        # Derive a strong 32-byte key
        key_bytes = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=16384,
            r=8,
            p=1,
            dklen=32,
        )
        derived_key = b64encode(key_bytes).decode("utf-8")

        cls._master_key = derived_key
        logger.info("Vault unlocked using provided password.")

        if _keyring_available() and _save_to_keyring(derived_key):
            logger.info("Derived Master Key securely saved to OS keyring for future use.")

        return derived_key

    @classmethod
    def _reset_for_testing(cls) -> None:
        """Reset cached state. Only for unit tests."""
        cls._master_key = None
