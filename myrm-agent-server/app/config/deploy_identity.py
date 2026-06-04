"""Single-tenant deploy identity sentinel for dependency injection."""


async def get_deploy_identity() -> str:
    """Return deploy-mode identity sentinel for single-tenant runtime.

    - 'sandbox' when running inside a control-plane sandbox
    - 'local' for desktop / local WebUI
    """
    from app.config.deploy_mode import get_deploy_mode

    mode = get_deploy_mode().value
    return "sandbox" if mode == "sandbox" else "local"
