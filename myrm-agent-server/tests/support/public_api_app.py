"""Full public API surface as OpenAPI, generated once per process.

[INPUT]
- app.api.router.api_router (POS: 全部 REST 路由聚合)
- app.api.webui.router (POS: /webui 路由)
- app.api.internal.org_policy_sync / app.api.memory.operations.command_center* (POS: 条件挂载的路由)

[OUTPUT]
- public_api_openapi(): 路径表 + OpenAPI 生成期间捕获的 `Duplicate Operation ID` 警告

[POS]
架构测试共享的全量路由快照；不 import app.main（见 test_no_app_main_in_tests）。
单次生成并缓存，因为 FastAPI 只在首次 `openapi()` 时发出重复 operationId 警告。
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from functools import cache

from fastapi import FastAPI

API_PREFIX = "/api/v1"


@dataclass(frozen=True, slots=True)
class PublicApiOpenApi:
    paths: dict[str, dict[str, object]]
    duplicate_operation_ids: tuple[str, ...]


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
