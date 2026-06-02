"""Agent 服务模块

子模块:
- agent_service: Agent CRUD
- streaming: General Agent 流式执行
- search: Web 搜索
- backends: 数据库 Agent 后端实现
"""

__all__ = [
    "AgentService",
    "ai_agent_service_stream",
    "search_web_service",
]

_LAZY_IMPORTS: dict[str, tuple[str, str]] = {
    "AgentService": ("app.services.agent.agent_service", "AgentService"),
    "ai_agent_service_stream": ("app.services.agent.streaming", "ai_agent_service_stream"),
    "search_web_service": ("app.services.agent.search", "search_web_service"),
}


def __getattr__(name: str) -> object:
    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        from importlib import import_module

        return getattr(import_module(module_path), attr)

    # Allow natural subpackage access (e.g. `agent.backends.profile_backend`)
    from importlib import import_module

    try:
        return import_module(f".{name}", __name__)
    except ImportError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
