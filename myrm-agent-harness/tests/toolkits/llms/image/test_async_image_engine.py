"""Tests for AsyncImageGenerationTools enqueue path and payload_postprocessor hook."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from myrm_agent_harness.toolkits.llms.image.async_image_engine import AsyncImageGenerationTools
from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import SQLiteTaskStore, TaskStatus


@pytest.fixture
async def temp_store() -> SQLiteTaskStore:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        db_path = handle.name

    store = SQLiteTaskStore(db_path=db_path)
    await store.initialize()
    yield store
    Path(db_path).unlink(missing_ok=True)


_MODEL = "gpt-image-2.6-sunburst"


@pytest.mark.asyncio
async def test_generate_image_returns_the_task_id(temp_store: SQLiteTaskStore) -> None:
    engine = AsyncImageGenerationTools(ImageGenerationConfig(model=_MODEL), temp_store)

    task_id = await engine.generate_image("a blue circle", user_id="user-1")

    assert task_id.startswith("img-")
    task = await temp_store.get_task(task_id)
    assert task is not None
    assert task.status is TaskStatus.PENDING


@pytest.mark.asyncio
async def test_generate_image_persists_the_request_and_execution_snapshot(
    temp_store: SQLiteTaskStore,
) -> None:
    config = ImageGenerationConfig(model=_MODEL, api_key="sk-plain")
    engine = AsyncImageGenerationTools(config, temp_store)

    task_id = await engine.generate_image(
        "a red cube",
        size="1536x1024",
        quality="high",
        reference_image_urls=["media://ref1"],
        user_id="user-2",
        agent_id="agent-2",
        chat_id="chat-2",
    )

    task = await temp_store.get_task(task_id)
    assert task is not None
    assert task.payload["prompt"] == "a red cube"
    assert task.payload["size"] == "1536x1024"
    assert task.payload["quality"] == "high"
    assert task.payload["reference_image_urls"] == ["media://ref1"]
    assert task.payload["model"] == _MODEL
    assert task.payload["api_key"] == "sk-plain"
    assert task.payload["chat_id"] == "chat-2"
    assert task.payload["agent_id"] == "agent-2"


@pytest.mark.asyncio
async def test_the_allowed_roots_are_snapshotted_only_when_given(temp_store: SQLiteTaskStore) -> None:
    engine = AsyncImageGenerationTools(ImageGenerationConfig(model=_MODEL), temp_store)

    scoped = await temp_store.get_task(await engine.generate_image("a", allowed_roots=("/work/chat-1",)))
    unscoped = await temp_store.get_task(await engine.generate_image("b"))

    assert scoped is not None
    assert scoped.payload["allowed_roots"] == ["/work/chat-1"]
    assert unscoped is not None
    assert "allowed_roots" not in unscoped.payload


@pytest.mark.asyncio
async def test_the_payload_carries_no_fields_the_engine_does_not_honour(temp_store: SQLiteTaskStore) -> None:
    engine = AsyncImageGenerationTools(ImageGenerationConfig(model=_MODEL), temp_store)

    task_id = await engine.generate_image("a green triangle")

    task = await temp_store.get_task(task_id)
    assert task is not None
    assert {"style", "count", "n", "default_quality", "allow_private_networks"}.isdisjoint(task.payload)


@pytest.mark.asyncio
async def test_generate_image_applies_payload_postprocessor_before_persist(
    temp_store: SQLiteTaskStore,
) -> None:
    config = ImageGenerationConfig(model=_MODEL, api_key="sk-seal-me")

    def _seal(payload: dict[str, object]) -> dict[str, object]:
        sealed = dict(payload)
        if "api_key" in sealed:
            sealed["api_key_enc"] = f"enc:{sealed['api_key']}"
            del sealed["api_key"]
        return sealed

    engine = AsyncImageGenerationTools(
        config,
        temp_store,
        payload_postprocessor=_seal,
    )
    task_id = await engine.generate_image("a green triangle", user_id="user-3")

    task = await temp_store.get_task(task_id)
    assert task is not None
    assert "api_key" not in task.payload
    assert task.payload["api_key_enc"] == "enc:sk-seal-me"
