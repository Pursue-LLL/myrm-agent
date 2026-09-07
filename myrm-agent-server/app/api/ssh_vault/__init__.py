"""SSH Vault API package.

[INPUT]
- .router::router

[OUTPUT]
- router

[POS]
API package in app/api/ssh_vault/.
"""

from app.api.ssh_vault.router import router

__all__ = ["router"]
