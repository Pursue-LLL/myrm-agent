"""通用Agent工具模块

[INPUT]
- app.ai_agents.general_agent.tools._tool_layer_bootstrap (POS: 业务层工具层注册实现)

[OUTPUT]
- ensure_tool_layer_bootstrap: 首次调用时导入并注册业务层工具（幂等、线程安全）

[POS]
工具包门面。把重量级工具层注册从进程导入期推迟到首次使用/后台预热，避免 HTTP
服务启动时为注册工具而导入整个 Agent 工具链（含 litellm）。
"""

from __future__ import annotations

import threading

_bootstrap_lock = threading.Lock()
_bootstrapped = False


def ensure_tool_layer_bootstrap() -> None:
    """Register server-layer tools once, on first use.

    Importing the bootstrap module pulls in the full agent tool chain (including
    litellm), so it must not run at HTTP-server import time. Agent creation awaits
    this in a worker thread; startup preloads it in the background.
    """
    global _bootstrapped
    if _bootstrapped:
        return
    with _bootstrap_lock:
        if _bootstrapped:
            return
        from . import _tool_layer_bootstrap  # noqa: F401  (import registers the layers)

        _bootstrapped = True
