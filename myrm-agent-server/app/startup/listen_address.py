"""
@input: 依赖 app.config.settings（端口 / WebUI 配置）、app.config.deploy_mode（运行方式）、app.server.runtime_dev_info（health 的监听信息）
@output: 对外提供 publish_listen_address —— 解析本进程应绑定的 (host, port)，并在服务器绑定前同步给 /api/v1/health
@pos: 桌面 sidecar（PyInstaller 入口 app/main.py）的监听地址解析；run.py 自行探测可用端口后直接调用 set_runtime_listen

🔄 更新规则：修改此文件后，请更新头注释 + 所属文件夹 _ARCH.md
"""

from __future__ import annotations

import logging

from app.config.deploy_mode import is_webui_mode
from app.config.settings import settings
from app.server.runtime_dev_info import DevMode, set_runtime_listen

logger = logging.getLogger(__name__)


def publish_listen_address() -> tuple[str, int]:
    """Resolve the address this process must bind and record it for ``/api/v1/health``.

    The packaged client can run on a non-default port; without this the health payload keeps
    reporting the module default instead of the port the server actually listens on.
    """
    dev_mode: DevMode
    if is_webui_mode():
        port = settings.webui.port
        dev_mode = "standalone_webui"
        if settings.webui.allow_remote:
            host = "0.0.0.0"
            logger.info("Starting in WebUI Remote mode: %s:%d", host, port)
        else:
            host = "127.0.0.1"
            logger.info("Starting in WebUI Local mode: %s:%d", host, port)
    else:
        host = "127.0.0.1"
        port = settings.port
        dev_mode = "split_dev"
        logger.info("Starting in Desktop Sidecar mode: %s:%d", host, port)

    set_runtime_listen(port=port, host=host, dev_mode=dev_mode)
    return host, port
