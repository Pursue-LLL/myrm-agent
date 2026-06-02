"""Database-backed implementation of AgentSecretBackend."""

import logging

from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto
from sqlalchemy import select

from app.core.security import MasterKeyProvider
from app.database.connection import get_session
from app.database.models import AgentSecret

logger = logging.getLogger(__name__)


class DatabaseSecretBackend:
    """Database-backed agent secrets store (async).

    Implements the same methods as the harness ``AgentSecretBackend`` protocol
    without nominal inheritance (the upstream protocol is untyped in stubs).

    Uses SQLAlchemy to store and retrieve agent secrets from the `agent_secrets` table.
    Integrates with MasterKeyProvider for secure AES-256-GCM encryption.
    """

    def __init__(self, master_key: str | None = None):
        """Initialize the DatabaseSecretBackend.

        Args:
            master_key: The master key used for encryption. If not provided,
                        it will be fetched from MasterKeyProvider.
        """
        self.master_key = master_key or MasterKeyProvider.get_master_key()
        # ConfigCrypto methods are static, we just need the derived key
        self._key = ConfigCrypto.derive_key(self.master_key)

    async def get_secret(self, agent_id: str, key: str) -> str | None:
        """Get a specific secret for an agent."""
        async with get_session() as db:
            result = await db.execute(select(AgentSecret).where(AgentSecret.agent_id == agent_id, AgentSecret.secret_key == key))
            secret = result.scalar_one_or_none()

            if not secret:
                return None

            try:
                return str(ConfigCrypto.decrypt_value(secret.secret_value, self._key)["value"])
            except Exception as e:
                logger.error(f"Failed to decrypt secret '{key}' for agent {agent_id}: {e}")
                return None

    async def get_all_secrets(self, agent_id: str) -> dict[str, str]:
        """Get all secrets for an agent."""
        async with get_session() as db:
            result = await db.execute(select(AgentSecret).where(AgentSecret.agent_id == agent_id))
            secrets = result.scalars().all()

            decrypted_secrets = {}
            for secret in secrets:
                try:
                    decrypted_secrets[secret.secret_key] = str(
                        ConfigCrypto.decrypt_value(secret.secret_value, self._key)["value"]
                    )
                except Exception as e:
                    logger.error(f"Failed to decrypt secret '{secret.secret_key}' for agent {agent_id}: {e}")

            return decrypted_secrets

    async def save_secret(self, agent_id: str, key: str, value: str, description: str | None = None) -> None:
        """Save a secret for an agent."""
        try:
            encrypted_value = ConfigCrypto.encrypt_value({"value": value}, self._key)
        except Exception as e:
            logger.error(f"Failed to encrypt secret '{key}' for agent {agent_id}: {e}")
            raise

        async with get_session() as db:
            result = await db.execute(select(AgentSecret).where(AgentSecret.agent_id == agent_id, AgentSecret.secret_key == key))
            secret = result.scalar_one_or_none()

            if secret:
                secret.secret_value = encrypted_value
                if description is not None:
                    secret.description = description
            else:
                import uuid

                secret = AgentSecret(
                    id=str(uuid.uuid4()),
                    agent_id=agent_id,
                    secret_key=key,
                    secret_value=encrypted_value,
                    description=description,
                )
                db.add(secret)

            await db.commit()

    async def delete_secret(self, agent_id: str, key: str) -> bool:
        """Delete a specific secret for an agent."""
        async with get_session() as db:
            result = await db.execute(select(AgentSecret).where(AgentSecret.agent_id == agent_id, AgentSecret.secret_key == key))
            secret = result.scalar_one_or_none()

            if secret:
                await db.delete(secret)
                await db.commit()
                return True
            return False

    async def delete_all_secrets(self, agent_id: str) -> bool:
        """Delete all secrets for an agent."""
        async with get_session() as db:
            result = await db.execute(select(AgentSecret).where(AgentSecret.agent_id == agent_id))
            secrets = result.scalars().all()

            if secrets:
                for secret in secrets:
                    await db.delete(secret)
                await db.commit()
                return True
            return False
