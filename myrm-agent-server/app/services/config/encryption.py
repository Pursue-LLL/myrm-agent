"""Business-layer config encryption service.

Injects encryption key and policy from settings. Decides when to encrypt
based on deploy mode and sensitive config keys.

[INPUT]
- myrm_agent_harness.utils.crypto::ConfigCrypto (framework-layer encryption tool)
- myrm_agent_harness.utils::resolve_local_encryption_key (POS: key resolution utility)
- app.config.settings::settings.config_encryption_key, settings.database.state_dir
- app.config.deploy_mode::is_sandbox, is_local_mode

[OUTPUT]
- ConfigEncryptionService: business-layer encryption service
- get_encryption_service: singleton factory

[POS]
Business-layer encryption policy. Framework provides tools; business layer
decides encryption strategy:
- Sandbox mode: uses settings.config_encryption_key (control plane provided)
- Local mode: resolves key via env var → file → auto-generate (portable, no hardware binding)
"""

from __future__ import annotations

import logging

from myrm_agent_harness.utils.crypto import ConfigCrypto, DecryptionError, EncryptionError

logger = logging.getLogger(__name__)

# Config keys whose values are encrypted at rest in SQLite
SENSITIVE_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "providers",
        "retrieval",
        "searchServices",
        "mcpServers",
        "orgMcpServers",
        "feishuCredentials",
        "dingtalkCredentials",
        "slackCredentials",
        "qqCredentials",
        "discordCredentials",
        "wecomCredentials",
        "wecomAibotCredentials",
        "wechatCredentials",
        "teamsCredentials",
        "matrixCredentials",
        "telegramCredentials",
        "googlechatCredentials",
        "smsCredentials",
        "vercelDeployCredentials",
        "browserCloudProvider",
        "browserProxy",
        "captchaSolverConfig",
        "webFetchEscalation",
    }
)


def is_sensitive_config(key: str) -> bool:
    """Check whether a config key contains sensitive data (API keys etc.)."""
    return key in SENSITIVE_CONFIG_KEYS


class ConfigEncryptionService:
    """Business-layer encryption service with policy injection.

    Decides when to encrypt based on:
    - Deployment mode (both Local and Sandbox modes encrypt sensitive data)
    - Sensitive config keys (SENSITIVE_CONFIG_KEYS)

    Encryption key sources:
    - Sandbox mode: settings.config_encryption_key (control plane provided)
    - Local mode: env var CONFIG_ENCRYPTION_KEY → file ~/.myrm/.encryption_key → auto-generate
    """

    def __init__(self, encryption_key: bytes | None, is_sandbox: bool, is_local: bool):
        """Initialize encryption service.

        Args:
            encryption_key: Encryption key (bytes, already derived)
            is_sandbox: Whether in sandbox mode
            is_local: Whether in local mode
        """
        self._key = encryption_key
        self._is_sandbox = is_sandbox
        self._is_local = is_local

    @property
    def has_key(self) -> bool:
        """Whether an encryption key is available."""
        return self._key is not None

    @property
    def raw_key(self) -> bytes | None:
        """Raw encryption key bytes (for low-level crypto operations like migration)."""
        return self._key

    def should_encrypt(self, config_key: str) -> bool:
        """Determine if encryption is needed (business policy).

        Args:
            config_key: Config key to check

        Returns:
            True if should encrypt (both modes + sensitive keys)
        """
        return (self._is_sandbox or self._is_local) and is_sensitive_config(config_key)

    def encrypt_if_needed(self, key: str, value: dict[str, object]) -> tuple[dict[str, object] | str, bool]:
        """Conditionally encrypt based on policy.

        Args:
            key: Config key
            value: Config value dict

        Returns:
            (encrypted_value, is_encrypted) tuple

        Raises:
            EncryptionError: If encryption fails
        """
        if self.should_encrypt(key):
            try:
                return ConfigCrypto.encrypt_value(value, self._key), True

            except EncryptionError as e:
                logger.error(f"Failed to encrypt config '{key}': {e}")
                raise
        return value, False

    def decrypt(self, ciphertext: str) -> dict[str, object]:
        """Decrypt config value.

        Args:
            ciphertext: Base64-encoded ciphertext

        Returns:
            Decrypted config dict

        Raises:
            DecryptionError: If decryption fails (wrong key or corrupted data)
        """
        try:
            return ConfigCrypto.decrypt_value(ciphertext, self._key)  # type: ignore
        except DecryptionError as e:
            logger.error(f"Failed to decrypt config: {e}")
            raise


# Singleton instance
_encryption_service: ConfigEncryptionService | None = None


def get_encryption_service() -> ConfigEncryptionService:
    """Get encryption service singleton (with injected configuration).

    Key resolution:
    - Sandbox mode: settings.config_encryption_key (control plane provided)
    - Local mode: env var → key file → auto-generate (portable, no hardware binding)

    Returns:
        ConfigEncryptionService singleton
    """
    global _encryption_service
    if not _encryption_service:
        from myrm_agent_harness.utils import resolve_local_encryption_key

        from app.config.deploy_mode import is_local_mode
        from app.config.settings import settings
        from app.platform_utils.deployment_capabilities import get_deployment_capabilities

        caps = get_deployment_capabilities()
        sandbox = caps.uses_config_encryption
        local = is_local_mode()

        if sandbox:
            encryption_key_str = settings.config_encryption_key.get_secret_value()
            encryption_key = ConfigCrypto.derive_key(encryption_key_str)
        elif local:
            encryption_key = resolve_local_encryption_key(settings.database.state_dir)
        else:
            encryption_key = None

        _encryption_service = ConfigEncryptionService(
            encryption_key=encryption_key,
            is_sandbox=sandbox,
            is_local=local,
        )
    return _encryption_service
