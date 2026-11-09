"""[INPUT]
- app.core.security.master_key::VaultLockedError (POS: 金库锁定错误)

[OUTPUT]
- vault_locked_error: 把锁定错误映射为 HTTP 423

[POS]
Vault HTTP 错误映射。WebUI 以 423 触发解锁流程，所有依赖金库的路由都必须用它，避免退化成 500。
"""

from fastapi import HTTPException, status

from app.core.security.master_key import VaultLockedError


def vault_locked_error(exc: VaultLockedError) -> HTTPException:
    """Translate a locked-vault failure into the 423 the client already knows how to handle."""
    return HTTPException(status_code=status.HTTP_423_LOCKED, detail=str(exc))
