"""Service for managing Vault Credentials."""

import logging
import uuid
from typing import Sequence

from myrm_agent_harness.toolkits.security.credential_vault import CredentialEntry, get_global_credential_vault
from myrm_agent_harness.utils.crypto.config_crypto import ConfigCrypto
from sqlalchemy import select

from app.core.security import MasterKeyProvider
from app.database.connection import get_session
from app.database.models import VaultCredential

logger = logging.getLogger(__name__)


class VaultCredentialService:
    """Service for managing Vault Credentials in SQLite and syncing to Harness."""

    def __init__(self, master_key: str | None = None):
        self.master_key = master_key or MasterKeyProvider.get_master_key()
        self._key = ConfigCrypto.derive_key(self.master_key)

    async def list_credentials(self) -> Sequence[VaultCredential]:
        """List all credentials (without decrypting secrets)."""
        async with get_session() as db:
            result = await db.execute(select(VaultCredential))
            return result.scalars().all()

    async def get_credential(self, label: str) -> VaultCredential | None:
        """Get a specific credential."""
        async with get_session() as db:
            result = await db.execute(select(VaultCredential).where(VaultCredential.label == label))
            return result.scalar_one_or_none()

    async def save_credential(
        self, label: str, password: str | None = None, totp_seed: str | None = None, description: str | None = None
    ) -> VaultCredential:
        """Save a credential and sync it to the global vault."""
        encrypted_password = None
        if password:
            try:
                encrypted_password = ConfigCrypto.encrypt_value({"value": password}, self._key)
            except Exception as e:
                logger.error(f"Failed to encrypt password for label '{label}': {e}")
                raise

        encrypted_totp_seed = None
        if totp_seed:
            try:
                encrypted_totp_seed = ConfigCrypto.encrypt_value({"value": totp_seed}, self._key)
            except Exception as e:
                logger.error(f"Failed to encrypt TOTP seed for label '{label}': {e}")
                raise

        async with get_session() as db:
            result = await db.execute(select(VaultCredential).where(VaultCredential.label == label))
            cred = result.scalar_one_or_none()

            if cred:
                if password is not None:
                    cred.encrypted_password = encrypted_password
                if totp_seed is not None:
                    cred.encrypted_totp_seed = encrypted_totp_seed
                if description is not None:
                    cred.description = description
            else:
                cred = VaultCredential(
                    id=uuid.uuid4().hex,
                    label=label,
                    encrypted_password=encrypted_password,
                    encrypted_totp_seed=encrypted_totp_seed,
                    description=description,
                )
                db.add(cred)

            await db.commit()
            await db.refresh(cred)

        # Sync to global vault
        vault = get_global_credential_vault()
        vault.add_credential(CredentialEntry(label=label, password=password, totp_seed=totp_seed))

        return cred

    async def delete_credential(self, label: str) -> bool:
        """Delete a credential and remove from global vault."""
        async with get_session() as db:
            result = await db.execute(select(VaultCredential).where(VaultCredential.label == label))
            cred = result.scalar_one_or_none()

            if cred:
                await db.delete(cred)
                await db.commit()
                
                # Remove from global vault
                vault = get_global_credential_vault()
                vault.remove_credential(label)
                return True
            return False

    async def sync_all_to_vault(self) -> None:
        """Load all credentials from SQLite, decrypt them, and populate the global vault.
        Should be called on server startup.
        """
        vault = get_global_credential_vault()
        vault.clear()
        
        creds = await self.list_credentials()
        for cred in creds:
            password = None
            if cred.encrypted_password:
                try:
                    password = str(ConfigCrypto.decrypt_value(cred.encrypted_password, self._key)["value"])
                except Exception as e:
                    logger.error(f"Failed to decrypt password for label '{cred.label}': {e}")
                    
            totp_seed = None
            if cred.encrypted_totp_seed:
                try:
                    totp_seed = str(ConfigCrypto.decrypt_value(cred.encrypted_totp_seed, self._key)["value"])
                except Exception as e:
                    logger.error(f"Failed to decrypt TOTP seed for label '{cred.label}': {e}")
                    
            vault.add_credential(CredentialEntry(label=cred.label, password=password, totp_seed=totp_seed))
            
        logger.info(f"Synced {len(creds)} credentials to the global CredentialVault.")
