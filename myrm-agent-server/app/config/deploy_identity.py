"""Single-tenant deploy identity sentinel for dependency injection.

[INPUT]
app.config.deploy_mode::get_deploy_mode (POS: 部署模式检测)

[OUTPUT]
get_deploy_identity: 返回 local/sandbox 身份哨兵字符串

[POS]
配置层部署身份，供 FastAPI Depends 与 memory manager_deps 使用。
"""


async def get_deploy_identity() -> str:
    """Return deploy-mode identity sentinel for single-tenant runtime.

    - 'sandbox' when running inside a control-plane sandbox
    - 'local' for desktop / local WebUI
    """
    from app.config.deploy_mode import get_deploy_mode

    mode = get_deploy_mode().value
    return "sandbox" if mode == "sandbox" else "local"
