"""Integration: GeneralAgent wiring → image_tool async enqueue (no LLM flake)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.ai_agents.agents import ImageGenerationParams
from app.ai_agents.general_agent.agent import GeneralAgent
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskFilters


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
    assert task.payload["api_key"] == "sk-wiring-int"
    assert task.payload["chat_id"] == "chat-wiring-int"
    assert task.payload["agent_id"] == "agent-wiring-int"

    listed = await image_task_store.list_tasks(TaskFilters(task_type="image_generate", limit=5))
    assert any(row.task_id == task.task_id for row in listed)
