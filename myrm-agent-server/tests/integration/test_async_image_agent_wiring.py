"""Integration: GeneralAgent wiring → image_tool async enqueue (no LLM flake)."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskFilters

from app.ai_agents.agents import ImageGenerationParams
from app.ai_agents.general_agent.agent import GeneralAgent


@pytest.fixture(autouse=True)
def _local_encryption() -> None:
    import app.services.config.encryption as enc_mod

    original = os.environ.get("DEPLOY_MODE")
    os.environ["DEPLOY_MODE"] = "local"
    enc_mod._encryption_service = None
    yield
    enc_mod._encryption_service = None
    if original is None:
        os.environ.pop("DEPLOY_MODE", None)
    else:
        os.environ["DEPLOY_MODE"] = original


@pytest.fixture
def image_task_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> SQLiteTaskStore:
    db_path = tmp_path / "agent-wiring-tasks.db"
    store = SQLiteTaskStore(db_path=str(db_path))

    async def _init() -> SQLiteTaskStore:
        await store.initialize()
        return store

    initialized = asyncio.run(_init())
    monkeypatch.setattr("app.lifecycle.task_worker._task_store_instance", initialized)
    return initialized


@pytest.mark.integration
@pytest.mark.asyncio
async def test_general_agent_image_tool_enqueues_task_with_chat_and_agent_ids(
    image_task_store: SQLiteTaskStore,
) -> None:
    """Full tool_setup wiring: image_tool generate must enqueue with payload snapshot."""
    from app.core.types import ModelConfig

    agent = GeneralAgent(
        model_cfg=ModelConfig(model="test/model", api_key="chat-key"),
        mcp_config=None,
        enable_web_search=False,
        chat_id="chat-wiring-int",
        agent_id="agent-wiring-int",
        image_generation_params=ImageGenerationParams(model="flux-pro", api_key="sk-wiring-int"),
    )
    agent._task_user_id = "user-wiring-int"

    tools: list[object] = []
    discoverable: list[object] = []
    agent._setup_search_and_basic_tools(tools, discoverable)

    image_tools = [tool for tool in tools if getattr(tool, "name", None) == "image_tool"]
    assert len(image_tools) == 1

    raw = await image_tools[0].ainvoke(
        {
            "action": "generate",
            "prompt": "a green triangle",
            "size": "512x512",
        }
    )
    payload = json.loads(str(raw))
    assert payload.get("task_id")
    assert payload.get("status") == "pending"

    task = await image_task_store.get_task(str(payload["task_id"]))
    assert task is not None
    assert task.payload["model"] == "flux-pro"
    assert "api_key" not in task.payload
    assert isinstance(task.payload.get("api_key_enc"), str)
    assert task.payload["chat_id"] == "chat-wiring-int"
    assert task.payload["agent_id"] == "agent-wiring-int"

    listed = await image_task_store.list_tasks(TaskFilters(task_type="image_generate", limit=5))
    assert any(row.task_id == task.task_id for row in listed)
