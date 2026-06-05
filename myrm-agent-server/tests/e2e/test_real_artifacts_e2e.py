"""真实端到端集成测试 - Artifacts 生成流程

使用完整 FastAPI app + 真实模型 + 内存 SQLite，不 mock agent 执行链路。
Provider 配置写入真实 DB（非 patch load_user_configs）。
"""

from __future__ import annotations

import json
import os
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

# Must be set BEFORE importing app
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///file:testdb_{uuid.uuid4().hex}?mode=memory&cache=shared&uri=true"

from app.main import app
from tests.api.agent.utils import (
    _infer_provider_id,
    _require_env,
    _strip_provider_prefix,
    get_model_selection,
    get_search_service_config,
)


def _build_providers_config() -> dict[str, object]:
    basic_model = _require_env("BASIC_MODEL")
    basic_key = os.getenv("BASIC_API_KEY", "test-api-key")
    basic_url = os.getenv("BASIC_BASE_URL")
    basic_pid = _infer_provider_id(basic_model)

    lite_model = _require_env("LITE_MODEL")
    lite_key = os.getenv("LITE_API_KEY", basic_key)
    lite_url = os.getenv("LITE_BASE_URL", basic_url)
    lite_pid = _infer_provider_id(lite_model)

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

    return {"providers": providers}


def _build_search_services_config() -> dict[str, object]:
    return {
        "searchServiceConfigs": [
            {
                "enabled": True,
                "role": "primary",
                "search_service": os.getenv("SEARCH_SERVICE", "tavily"),
                "api_key": os.getenv("TAVILY_API_KEY", "test-tavily-key"),
            }
        ]
    }


async def _seed_user_configs() -> None:
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.database.models import UserConfig
    from app.platform_utils import get_database_engine

    engine = get_database_engine()
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        session.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="providers",
                config_value=_build_providers_config(),
                version="e2e_1",
                last_device_id="e2e-test",
                is_encrypted=False,
            )
        )
        session.add(
            UserConfig(
                id=str(uuid.uuid4()),
                config_key="searchServices",
                config_value=_build_search_services_config(),
                version="e2e_1",
                last_device_id="e2e-test",
                is_encrypted=False,
            )
        )
        await session.commit()

    invalidate_user_configs_cache()


@pytest.fixture(autouse=True)
async def setup_e2e_database(monkeypatch: pytest.MonkeyPatch) -> None:
    from sqlalchemy import text

    import app.database.models  # noqa: F401 — register all tables on Base.metadata
    from app.core.channel_bridge.config_cache import invalidate_user_configs_cache
    from app.database.models import Base
    from app.database.repositories.conversation_recall_repo import (
        CONVERSATION_RECALL_SCHEMA_SQL,
    )
    from app.platform_utils import get_database_engine, reset_database_engine

    monkeypatch.setenv("BASIC_MODEL", "minimax/MiniMax-M2.7")
    monkeypatch.setenv("BASIC_API_KEY", os.environ.get("LITE_API_KEY", ""))
    monkeypatch.setenv("BASIC_BASE_URL", os.environ.get("LITE_BASE_URL", ""))

    await reset_database_engine()
    engine = get_database_engine()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for sql in CONVERSATION_RECALL_SCHEMA_SQL:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass

    await _seed_user_configs()
    invalidate_user_configs_cache()
    yield


def _run_agent_until_settled(client: TestClient, req_data: dict[str, object]) -> list[dict[str, object]]:
    collected_data: list[dict[str, object]] = []
    for _round_idx in range(5):
        with client.stream("POST", "/api/v1/agents/agent-stream", json=req_data) as response:
            if response.status_code != 200:
                body = response.read().decode("utf-8", errors="replace")
                pytest.fail(f"Agent stream failed ({response.status_code}): {body}")
            for line in response.iter_lines():
                if not line or not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if isinstance(data, dict):
                        collected_data.append(data)
                except json.JSONDecodeError:
                    continue

        approval_required = any(
            data.get("type") in ("approval_required", "tool_approval_request") for data in collected_data[-10:]
        )
        if not approval_required:
            break

        req_data["resumeValue"] = [{"type": "approve", "extensions": {"allowAlways": True}}]

    error_events = [d for d in collected_data if d.get("type") == "error"]
    if error_events:
        error_msg = str(error_events[0].get("error", ""))
        if any(
            kw in error_msg
            for kw in (
                "Authentication",
                "authorized_error",
                "APIConnectionError",
                "401",
                "403",
                "no such table",
            )
        ):
            if "no such table" in error_msg:
                pytest.fail(f"E2E database schema not initialized: {error_msg[:200]}")
            pytest.skip(f"Model auth unavailable in e2e environment: {error_msg[:200]}")
        pytest.fail(f"Agent execution error: {error_msg}")
    return collected_data


def _poll_target_artifact(
    client: TestClient,
    *,
    filename: str,
    attempts: int = 12,
    interval_s: float = 0.5,
) -> dict[str, object] | None:
    for _ in range(attempts):
        res = client.get("/api/v1/files/artifacts/")
        assert res.status_code == 200
        artifacts = res.json().get("artifacts", [])
        for artifact in artifacts:
            if artifact.get("name") == filename:
                return artifact
        time.sleep(interval_s)
    return None


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY"),
    reason="需要 BASIC_API_KEY 以调用真实模型",
)
@pytest.mark.asyncio
async def test_real_artifact_generation_e2e() -> None:
    """测试真实的 Artifact 流程，不使用 load_user_configs mock"""
    client = TestClient(app)
    model_selection = get_model_selection()
    search_config = get_search_service_config()
    query = (
        "Call file_write_tool NOW. Write exactly '# Hello Integration Test' to "
        "real_test_artifact.md. Do NOT use bash_code_execute_tool or planner_tool."
    )

    target_artifact: dict[str, object] | None = None
    for attempt in range(3):
        chat_id = f"real-artifact-{uuid.uuid4().hex[:8]}"
        req_data: dict[str, object] = {
            "messageId": f"real-msg-{attempt}",
            "chatId": chat_id,
            "query": query,
            "modelSelection": model_selection,
            "searchServiceCfg": search_config,
            "agentConfig": {"enabledBuiltinTools": ["file_write_tool"]},
        }
        _run_agent_until_settled(client, req_data)
        target_artifact = _poll_target_artifact(client, filename="real_test_artifact.md")
        if target_artifact is not None:
            break

    assert target_artifact is not None, "real_test_artifact.md was not found after 3 attempts"
