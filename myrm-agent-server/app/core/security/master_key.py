"""
[INPUT]
None

[OUTPUT]
VaultLockedError: 当缺少主密钥且金库锁定且无法获取时抛出
MasterKeyProvider: 为单机业务容器提供主密钥派生和内存保管服务

[POS]
安全金库密钥派生模块。提供零落盘的主密钥内存派生与验证服务，保护凭证安全。
"""

import hashlib
import logging
import os
from base64 import b64encode

logger = logging.getLogger(__name__)

_KEYRING_SERVICE = "myrm-agent-vault"
_KEYRING_ACCOUNT = "master-key"


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


def _load_from_keyring() -> str | None:
    """Attempt to load the master key from the OS keyring."""
    try:
        import keyring

        value = keyring.get_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT)
        return value if value else None
    except Exception as e:
        logger.debug(f"Keyring read failed (non-fatal): {e}")
        return None


def _save_to_keyring(key: str) -> bool:
    """Attempt to save the master key to the OS keyring."""
    try:
        import keyring

        keyring.set_password(_KEYRING_SERVICE, _KEYRING_ACCOUNT, key)
        return True
    except Exception as e:
        logger.debug(f"Keyring write failed (non-fatal): {e}")
        return False


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
