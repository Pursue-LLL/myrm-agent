"""Agent 测试共享 fixtures

提供最小化测试配置，避免加载完整 API 栈。
Mock 数据库依赖、工具审批、MCP 全局状态，使测试无需真实 DB 即可运行。
"""

import logging
import os
import random
import sys
from importlib import import_module
from pathlib import Path
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.database.repositories.uow
from tests.api.agent.utils import (
    _infer_provider_id,
    _require_env,
    _strip_provider_prefix,
    build_memory_e2e_embedding_retrieval_dict,
)
from tests.support.test_secrets import resolve_test_env


def configure_test_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    console_handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    root_logger.setLevel(logging.WARNING)
    root_logger.addHandler(console_handler)
    logging.getLogger("myrm_agent_harness.toolkits.llms.utils.logger").setLevel(logging.WARNING)


configure_test_logging()


def _build_mock_user_configs() -> object:
    """构建测试用的 UserConfigs mock 对象

    当 BASIC_MODEL 和 LITE_MODEL 指向同一个 provider 时，合并为一个 provider
    以避免 _resolve_model_config 中 next() 匹配到错误的 provider。
    """
    from app.core.channel_bridge.config_loader import UserConfigs
    from app.core.channel_bridge.config_parsers import (
        extract_active_search_config,
        is_search_user_configured,
    )
    from app.core.types import ModelConfig

    basic_model = _require_env("BASIC_MODEL")
    basic_key = resolve_test_env("BASIC_API_KEY", "test-api-key")
    basic_url = resolve_test_env("BASIC_BASE_URL")
    basic_pid = _infer_provider_id(basic_model)

    lite_model = _require_env("LITE_MODEL")
    lite_key = resolve_test_env("LITE_API_KEY", basic_key)
    lite_url = resolve_test_env("LITE_BASE_URL", basic_url or "")
    lite_pid = _infer_provider_id(lite_model)

    if not os.getenv("OPENAI_API_KEY"):
        os.environ["OPENAI_API_KEY"] = basic_key

    model_cfg = ModelConfig(model=basic_model, api_key=basic_key, base_url=basic_url)
    search_services_dict: dict[str, object] = {
        "searchServiceConfigs": [
            {
                "enabled": True,
                "role": "primary",
                "search_service": resolve_test_env("SEARCH_SERVICE", "tavily"),
                "api_key": resolve_test_env("TAVILY_API_KEY", "test-tavily-key"),
            }
        ]
    }
    search_cfg = extract_active_search_config(search_services_dict)
    search_configured = is_search_user_configured(search_services_dict)

    basic_stripped = _strip_provider_prefix(basic_model)
    lite_stripped = _strip_provider_prefix(lite_model)

    def _provider_type(provider_id: str) -> str:
        normalized = provider_id.replace("-", "_")
        if normalized == "minimax":
            return "minimax"
        if normalized in {"openai", "openai_like", "openai_compatible"}:
            return "openai"
        return normalized

    if basic_pid == lite_pid:
        providers: list[dict[str, object]] = [
            {
                "id": basic_pid,
                "providerType": _provider_type(basic_pid),
                "isEnabled": True,
                "apiUrl": basic_url,
                "apiKeys": [{"key": basic_key, "isActive": True}],
                "enabledModels": list({basic_stripped, lite_stripped}),
            },
        ]
    else:
        providers = [
            {
                "id": basic_pid,
                "providerType": _provider_type(basic_pid),
                "isEnabled": True,
                "apiUrl": basic_url,
                "apiKeys": [{"key": basic_key, "isActive": True}],
                "enabledModels": [basic_stripped],
            },
            {
                "id": lite_pid,
                "providerType": _provider_type(lite_pid),
                "isEnabled": True,
                "apiUrl": lite_url,
                "apiKeys": [{"key": lite_key, "isActive": True}],
                "enabledModels": [lite_stripped],
            },
        ]

    retrieval_dict = build_memory_e2e_embedding_retrieval_dict()

    return UserConfigs(
        model_cfg=model_cfg,
        search_cfg=search_cfg,
        search_is_user_configured=search_configured,
        retrieval_dict=retrieval_dict,
        personal_settings_dict=None,
        mcp_dict=None,
        providers_dict={
            "providers": providers,
            "defaultModelConfig": {
                "baseModel": {
                    "primary": {
                        "providerId": basic_pid,
                        "model": basic_stripped,
                    }
                }
            },
        },
        security_config_dict={"yoloModeEnabled": False, "autoModeEnabled": False},
    )


@pytest.fixture(scope="function")
def app() -> FastAPI:
    """创建最小化测试应用，mock 所有 DB 依赖"""
    app = FastAPI(title="Agent Test App")

    async def mock_get_deploy_identity() -> Optional[str]:
        return "test-user-id"

    pass
    pass

    general_agent_module = import_module("app.api.agents.general_agent")
    app.include_router(general_agent_module.router, prefix="/api/v1/agents", tags=["agents"])

    agent_management_module = import_module("app.api.agents.agent")
    app.include_router(agent_management_module.router, prefix="/api/agents", tags=["agent-management"])

    generate_prompt_module = import_module("app.api.agents.generate_prompt")
    app.include_router(generate_prompt_module.router, prefix="/api/agents", tags=["agent-management"])

    agent_history_module = import_module("app.api.agents.agent_history")
    app.include_router(agent_history_module.router, prefix="/api/agents", tags=["agent-management"])

    memory_module = import_module("app.api.memory.router")
    app.include_router(memory_module.router, prefix="/api/v1/memory", tags=["memory"])

    wiki_module = import_module("app.api.wiki.router")
    app.include_router(wiki_module.router, prefix="/api/v1/wiki", tags=["wiki"])

    # Add chat router for persistence tests
    chat_module = import_module("app.api.chats.chat")
    app.include_router(chat_module.router, prefix="/api/v1/chats", tags=["chats"])

    # Add files router for vault endpoints tests
    vault_module = import_module("app.api.files.vault_api")
    app.include_router(vault_module.router, prefix="/api/v1/files/vault", tags=["files-vault"])

    artifact_api_module = import_module("app.api.files.artifact_api")
    app.include_router(artifact_api_module.router, prefix="/api/v1/files/artifacts", tags=["files-artifacts"])

    goals_module = import_module("app.api.goals.router")
    app.include_router(goals_module.router, prefix="/api/v1", tags=["goals"])

    templates_module = import_module("app.api.agents.templates")
    app.include_router(templates_module.router, prefix="/api/v1/agents", tags=["agent-templates"])

    kanban_module = import_module("app.api.kanban.router")
    app.include_router(kanban_module.router, prefix="/api/v1")

    return app


@pytest.fixture(scope="function")
def client(app: FastAPI) -> TestClient:
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture(autouse=True)
async def setup_test_database(tmp_path: Path):
    """Initialize a file-backed SQLite database with schema for agent CRUD tests.

    Uses file-backed SQLite instead of in-memory to prevent data loss
    when connections are momentarily closed during long-running Agent tests.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    from app.database.models import Base

    db_file = tmp_path / "test_agent.db"
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{db_file}", poolclass=StaticPool, connect_args={"check_same_thread": False}
    )
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        # Create raw SQL tables (FTS5)
        from sqlalchemy import text

        from app.database.repositories.conversation_recall import CONVERSATION_RECALL_SCHEMA_SQL

        for sql in CONVERSATION_RECALL_SCHEMA_SQL:
            await conn.execute(text(sql))

    TestSession = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_get_session():
        async with TestSession() as session:
            try:
                yield session
            finally:
                await session.close()

    def mock_get_session_factory():
        return TestSession

    with (
        patch("app.database.connection.get_session", mock_get_session),
        patch("app.services.approvals.registry.get_session", mock_get_session),
        patch("app.platform_utils.get_session_factory", mock_get_session_factory),
        patch(
            "app.database.repositories.uow.get_session_factory",
            mock_get_session_factory,
        ),
        patch("app.database.connection.get_session_factory", mock_get_session_factory),
        patch("app.services.budget.enforcer.get_session_factory", mock_get_session_factory),
        patch("app.services.memory.shared_context.get_session", mock_get_session),
    ):
        yield

    # Try to clean up, but ignore database locked errors during teardown
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.drop_all)
    except Exception as e:
        import logging

        logging.getLogger(__name__).warning(f"Failed to drop test database tables: {e}")
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def mock_load_user_configs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Mock load_user_configs 避免真实 DB 查询"""
    memory_path = tmp_path / "memory"
    memory_path.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MEMORY_BASE_PATH", str(memory_path))
    mock_configs = _build_mock_user_configs()
    mock_fn = AsyncMock(return_value=mock_configs)

    with patch("app.core.channel_bridge.config_loader.load_user_configs", mock_fn):
        yield mock_fn


# Removed auto_approve_tools fixture - ApprovalDecision/ApprovalResponse API no longer exists
# Batch approval now uses { "decisions": [{"type": "approve", ...}] } format


@pytest.fixture(autouse=True)
def disable_memory_auto_extraction():
    """Disable background memory extraction in tests.

    auto_extract_memories runs LLM-generated bash commands that time out in
    test environments (no /persistent volume), adding ~60s per test run.
    """

    async def _noop(*args: object, **kwargs: object) -> None:
        return

    with patch(
        "myrm_agent_harness.agent._internals.memory_extraction.auto_extract_memories",
        new=_noop,
    ):
        yield


@pytest.fixture(autouse=True)
def disable_commitment_extraction():
    """Disable commitment extraction in tests.

    Commitment extraction is a fire-and-forget background task that races with
    fixture teardown (SQLite tables already dropped). Since MCP tests don't
    exercise this feature, mock it out to eliminate log noise.
    """

    def _noop_factory(*args: object, **kwargs: object):
        async def _noop_extract(messages: object, chat_id: object) -> None:
            return

        return _noop_extract

    with patch(
        "app.ai_agents.general_agent.callbacks.make_commitment_extraction_callback",
        new=_noop_factory,
    ):
        yield


@pytest.fixture(autouse=True)
def reset_mcp_ipc_server():
    """重置全局 MCP IPC Server 状态，防止测试间 stale socket 导致连接失败"""
    yield
    import myrm_agent_harness.agent.skills.mcp.ipc_proxy as ipc_mod

    if ipc_mod._ipc_server is not None:
        ipc_mod._ipc_server._running = False
        ipc_mod._ipc_server = None


@pytest.fixture(autouse=True)
def setup_random_mcp_port():
    """为每个测试分配随机 MCP HTTP 端口，避免端口冲突"""
    os.environ["MCP_HTTP_PORT"] = str(random.randint(10000, 60000))
    yield


def _clear_agent_test_process_state() -> None:
    import asyncio

    from myrm_agent_harness.agent.middlewares.approval.scheduler import ApprovalTimeoutScheduler

    from app.core.memory.adapters.setup import shutdown_cached_memory_managers
    from app.platform_utils import _reset_checkpointer_for_testing, _reset_quota_manager_for_testing

    _reset_checkpointer_for_testing()
    _reset_quota_manager_for_testing()
    ApprovalTimeoutScheduler.get().cancel_all()
    try:
        asyncio.run(shutdown_cached_memory_managers())
    except RuntimeError:
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(shutdown_cached_memory_managers())
        finally:
            loop.close()


@pytest.fixture(autouse=True)
def _reset_agent_test_singletons():
    """Reset process-level singletons that leak across agent API tests."""
    _clear_agent_test_process_state()

    from langgraph.checkpoint.memory import MemorySaver

    from app.platform_utils import set_checkpointer

    set_checkpointer(MemorySaver())
    yield
    _clear_agent_test_process_state()
