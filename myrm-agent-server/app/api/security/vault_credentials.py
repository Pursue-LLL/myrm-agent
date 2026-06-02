"""Vault Credentials CRUD API."""

import logging
from typing import Sequence

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.database.models.vault_credential import VaultCredential
from app.services.security.vault_credential_service import VaultCredentialService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vault-credentials", tags=["security", "vault"])


class VaultCredentialCreate(BaseModel):
    label: str
    password: str | None = None
    totp_seed: str | None = None
    description: str | None = None


class VaultCredentialUpdate(BaseModel):
    password: str | None = None
    totp_seed: str | None = None
    description: str | None = None


class VaultCredentialResponse(BaseModel):
    id: str
    label: str
    description: str | None = None
    has_password: bool
    has_totp_seed: bool

    @classmethod
    def from_orm(cls, cred: VaultCredential) -> "VaultCredentialResponse":
        return cls(
            id=cred.id,
            label=cred.label,
            description=cred.description,
            has_password=bool(cred.encrypted_password),
            has_totp_seed=bool(cred.encrypted_totp_seed),
        )


@router.get("", response_model=list[VaultCredentialResponse])
async def list_credentials() -> list[VaultCredentialResponse]:
    """List all vault credentials (metadata only, secrets are not returned)."""
    try:
        service = VaultCredentialService()
        creds = await service.list_credentials()
        return [VaultCredentialResponse.from_orm(c) for c in creds]
    except Exception as e:
        logger.error(f"Failed to list vault credentials: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("", response_model=VaultCredentialResponse, status_code=status.HTTP_201_CREATED)
async def create_credential(req: VaultCredentialCreate) -> VaultCredentialResponse:
    """Create a new vault credential."""
    if not req.password and not req.totp_seed:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Must provide either password or totp_seed.")
        
    try:
        service = VaultCredentialService()
        existing = await service.get_credential(req.label)
        if existing:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Credential with label '{req.label}' already exists.")
            
        cred = await service.save_credential(
            label=req.label,
            password=req.password,
            totp_seed=req.totp_seed,
            description=req.description,
        )
        return VaultCredentialResponse.from_orm(cred)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create vault credential: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.put("/{label}", response_model=VaultCredentialResponse)
async def update_credential(label: str, req: VaultCredentialUpdate) -> VaultCredentialResponse:
    """Update an existing vault credential."""
    try:
        service = VaultCredentialService()
        existing = await service.get_credential(label)
        if not existing:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Credential '{label}' not found.")
            
        cred = await service.save_credential(
            label=label,
            password=req.password,
            totp_seed=req.totp_seed,
            description=req.description,
        )
        return VaultCredentialResponse.from_orm(cred)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update vault credential '{label}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.delete("/{label}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_credential(label: str) -> None:
    """Delete a vault credential."""
    try:
        service = VaultCredentialService()
        deleted = await service.delete_credential(label)
        if not deleted:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Credential '{label}' not found.")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete vault credential '{label}': {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
