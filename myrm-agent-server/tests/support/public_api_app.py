"""The public API as OpenAPI, generated once per process: every router except the ones `app.main` mounts itself.

[INPUT]
- app.api.router.api_router (POS: 全部 REST 路由聚合)
- app.api.webui.router (POS: /webui 路由)
- app.api.internal.org_policy_sync / app.api.memory 的 Labs 路由（command_center*、归档恢复、工具指引、画像笔记、首次见面、临时增量、认知时钟控制台、导入回滚预演、各引擎控制台）(POS: 条件挂载的路由)

[OUTPUT]
- public_api_openapi(): 路径表 + OpenAPI 生成期间捕获的 `Duplicate Operation ID` 警告 + 指向不存在组件的 `$ref`
- public_api_handlers(): 每个操作背后的端点函数（`app/` 下的文件 + 函数名 + 方法 + 客户端路径）
- build_public_api_app(): 每次新建一个挂好全部公开路由的应用；共享快照有缓存、不可改，要补挂路由的测试用这个
- API_VERBS: 计入「操作」的 HTTP 方法

[POS]
架构测试共享的路由快照；不 import app.main（见 test_no_app_main_in_tests），所以 `app/main.py` 直接挂载的内部/管理路由、`/mem0`、OpenAI 兼容接口与 `/health` 不在其中。
共享快照单次生成并缓存，因为 FastAPI 只在首次 `openapi()` 时发出重复 operationId 警告。端点函数经 `fastapi.routing.iter_route_contexts`
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
_SCHEMA_REF_PREFIX = "#/components/schemas/"


@dataclass(frozen=True, slots=True)
class PublicApiOpenApi:
    paths: dict[str, dict[str, object]]
    duplicate_operation_ids: tuple[str, ...]
    unresolved_schema_refs: tuple[str, ...]


def build_public_api_app() -> FastAPI:
    """A new app with every public router mounted, for a caller that mounts further routers on top of it.

    `public_api_openapi()` and `public_api_handlers()` read one cached instance of it, which must stay untouched.
    """
    from app.api.internal.org_policy_sync.org_model_policy_sync import frontend_router as org_policy_router
    from app.api.memory import onboarding
    from app.api.memory.budget_packing_router import router as budget_packing_router
    from app.api.memory.ephemeral_delta_router import router as ephemeral_delta_router
    from app.api.memory.markdown_chunker import router as markdown_chunker_router
    from app.api.memory.mem_cube_router import router as mem_cube_router
    from app.api.memory.operations import (
        archive_restore,
        cognitive_clock_console,
        command_center,
        command_center_consolidation,
        command_center_diagnostics,
        import_rollback_preview,
        tool_guidance,
    )
    from app.api.memory.private_notebook_router import router as private_notebook_router
    from app.api.memory.profile_notes_router import router as profile_notes_router
    from app.api.memory.score_honesty_router import router as score_honesty_router
    from app.api.memory.two_layer_dialectic_router import router as two_layer_dialectic_router
    from app.api.router import api_router
    from app.api.webui.router import router as webui_router
    from app.config.settings import settings

    app = FastAPI()
    app.include_router(api_router, prefix=API_PREFIX)
    app.include_router(org_policy_router, prefix=API_PREFIX)
    # The memory router mounts the lab routers only when MYRM_MEMORY_LABS is on; the client targets them either way,
    # so mount them here when they are not already part of api_router (mounting twice would duplicate operation ids).
    if not settings.memory_labs_enabled:
        for lab_router in (
            command_center.router,
            command_center_consolidation.router,
            command_center_diagnostics.router,
            archive_restore.router,
            tool_guidance.router,
            profile_notes_router,
            onboarding.router,
            ephemeral_delta_router,
            cognitive_clock_console.router,
            import_rollback_preview.router,
            private_notebook_router,
            two_layer_dialectic_router,
            budget_packing_router,
            mem_cube_router,
            markdown_chunker_router,
            score_honesty_router,
        ):
            app.include_router(lab_router, prefix=f"{API_PREFIX}/memory")
    app.include_router(webui_router)
    return app


@cache
def _shared_app() -> FastAPI:
    return build_public_api_app()


def _collect_schema_refs(node: object, refs: set[str]) -> None:
    """Add the component name of every ``$ref`` under ``node`` that points into ``#/components/schemas``."""
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and ref.startswith(_SCHEMA_REF_PREFIX):
            refs.add(ref.removeprefix(_SCHEMA_REF_PREFIX))
        for value in node.values():
            _collect_schema_refs(value, refs)
    elif isinstance(node, list):
        for item in node:
            _collect_schema_refs(item, refs)


def _unresolved_schema_refs(schema: dict[str, object]) -> tuple[str, ...]:
    components = schema.get("components")
    defined = components.get("schemas", {}) if isinstance(components, dict) else {}
    referenced: set[str] = set()
    _collect_schema_refs(schema, referenced)
    return tuple(sorted(referenced - set(defined)))


@cache
def public_api_openapi() -> PublicApiOpenApi:
    app = _shared_app()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = app.openapi()
    duplicates = tuple(str(w.message) for w in caught if "Duplicate Operation ID" in str(w.message))
    return PublicApiOpenApi(
        paths=schema["paths"],
        duplicate_operation_ids=duplicates,
        unresolved_schema_refs=_unresolved_schema_refs(schema),
    )


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
    for context in iter_route_contexts(_shared_app().routes):
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
