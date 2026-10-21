"""Full public API surface as OpenAPI, generated once per process.

[INPUT]
- app.api.router.api_router (POS: 全部 REST 路由聚合)
- app.api.webui.router (POS: /webui 路由)
- app.api.internal.org_policy_sync / app.api.memory.operations.command_center* (POS: 条件挂载的路由)

[OUTPUT]
- public_api_openapi(): 路径表 + OpenAPI 生成期间捕获的 `Duplicate Operation ID` 警告
- public_api_handlers(): 每个操作背后的端点函数（`app/` 下的文件 + 函数名 + 方法 + 客户端路径）
- API_VERBS: 计入「操作」的 HTTP 方法

[POS]
架构测试共享的全量路由快照；不 import app.main（见 test_no_app_main_in_tests）。
单次生成并缓存，因为 FastAPI 只在首次 `openapi()` 时发出重复 operationId 警告。端点函数经 `fastapi.routing.iter_route_contexts`
从同一个应用读出：函数名相同的端点（`create_task`、`create_job`）无法靠 operationId 区分文件。
"""

from __future__ import annotations

import inspect
import warnings
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import NamedTuple

from fastapi import FastAPI
from fastapi.routing import iter_route_contexts

API_PREFIX = "/api/v1"
API_VERBS = frozenset({"GET", "POST", "PUT", "DELETE", "PATCH"})
_APP_DIR = Path(__file__).resolve().parents[2] / "app"


@dataclass(frozen=True, slots=True)
class PublicApiOpenApi:
    paths: dict[str, dict[str, object]]
    duplicate_operation_ids: tuple[str, ...]


@cache
def _build_app() -> FastAPI:
    from app.api.internal.org_policy_sync.org_model_policy_sync import frontend_router as org_policy_router
    from app.api.memory.operations import command_center, command_center_consolidation, command_center_diagnostics
    from app.api.router import api_router
    from app.api.webui.router import router as webui_router
    from app.config.settings import settings

    app = FastAPI()
    app.include_router(api_router, prefix=API_PREFIX)
    app.include_router(org_policy_router, prefix=API_PREFIX)
    # The memory router mounts the lab routers only when MYRM_MEMORY_LABS is on; the client targets them either way,
    # so mount them here when they are not already part of api_router (mounting twice would duplicate operation ids).
    if not settings.memory_labs_enabled:
        for lab_router in (command_center.router, command_center_consolidation.router, command_center_diagnostics.router):
            app.include_router(lab_router, prefix=f"{API_PREFIX}/memory")
    app.include_router(webui_router)
    return app


@cache
def public_api_openapi() -> PublicApiOpenApi:
    app = _build_app()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = app.openapi()
    duplicates = tuple(str(w.message) for w in caught if "Duplicate Operation ID" in str(w.message))
    return PublicApiOpenApi(paths=schema["paths"], duplicate_operation_ids=duplicates)


class ApiHandler(NamedTuple):
    """The endpoint function behind one operation: its file under ``app/``, its name, the method and the client path."""

    file: str
    function: str
    method: str
    path: str


@cache
def public_api_handlers() -> tuple[ApiHandler, ...]:
    """Every operation of the public API with the ``app/`` function that serves it.

    An endpoint defined outside ``app/`` (the framework's own docs routes) is left out, and so is one wrapped by a
    decorator that hides the function it wraps; a caller must treat such an operation as unmapped, not as absent.
    """
    handlers: list[ApiHandler] = []
    for context in iter_route_contexts(_build_app().routes):
        endpoint = context.endpoint
        if endpoint is None or context.path_format is None:
            continue
        code = getattr(inspect.unwrap(endpoint), "__code__", None)
        source = Path(code.co_filename).resolve() if code is not None else None
        if code is None or source is None or not source.is_relative_to(_APP_DIR):
            continue
        file = str(source.relative_to(_APP_DIR))
        path = context.path_format.removeprefix(API_PREFIX)
        handlers.extend(
            ApiHandler(file, code.co_name, method, path) for method in sorted(context.methods or ()) if method in API_VERBS
        )
    return tuple(handlers)
