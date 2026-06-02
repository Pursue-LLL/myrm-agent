"""
[INPUT]
core.security.master_key::MasterKeyProvider (POS: 安全金库密钥派生模块)

[OUTPUT]
unlock_vault: 接收用户主密码并解锁金库

[POS]
金库解锁 API 路由。供无凭证环境（Local/Docker）的终端用户安全输入密码派生主密钥。
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.security.master_key import MasterKeyProvider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/vault", tags=["vault"])


class VaultUnlockRequest(BaseModel):
    password: str


class VaultUnlockResponse(BaseModel):
    status: str
    message: str


@router.post("/unlock", response_model=VaultUnlockResponse)
async def unlock_vault(req: VaultUnlockRequest) -> VaultUnlockResponse:
    """
    Unlock the Zero-Disk Vault by deriving the master key from the user's password.
    This is used in Local / Tauri deploy modes when OS Keyring is unavailable.
    """
    if not req.password:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Password is required to unlock the vault.")

    try:
        MasterKeyProvider.unlock_vault(req.password)
        return VaultUnlockResponse(status="success", message="Vault unlocked successfully.")
    except Exception as e:
        logger.error(f"Failed to unlock vault: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to unlock vault: {str(e)}") from e
