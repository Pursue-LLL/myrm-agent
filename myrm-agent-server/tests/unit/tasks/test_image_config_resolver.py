"""Tests for async image task config resolution."""

from __future__ import annotations

import os

import pytest

from myrm_agent_harness.toolkits.llms.image.models import ImageGenerationConfig
from myrm_agent_harness.toolkits.tasks import Task, TaskStatus

from app.tasks.image_config_resolver import resolve_image_generation_config
from app.tasks.task_payload_crypto import seal_task_payload_secrets


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


def test_resolve_image_generation_config_from_payload_snapshot() -> None:
    task = Task(
        task_id="img-test-1",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={
            "prompt": "a cat",
            "model": "flux-pro",
            "fallback_models": ["dall-e-3"],
            "default_size": "1792x1024",
            "default_quality": "hd",
            "timeout_seconds": 90,
            "max_retries": 2,
            "api_key": "sk-test",
            "chat_id": "chat-abc",
            "agent_id": "agent-xyz",
        },
    )

    config = resolve_image_generation_config(task)

    assert isinstance(config, ImageGenerationConfig)
    assert config.model == "flux-pro"
    assert config.fallback_models == ["dall-e-3"]
    assert config.default_size == "1792x1024"
    assert config.default_quality == "hd"
    assert config.timeout_seconds == 90
    assert config.max_retries == 2
    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "sk-test"
    assert config.media_callback is not None


def test_resolve_image_generation_config_defaults_without_snapshot_fields() -> None:
    task = Task(
        task_id="img-test-2",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload={"prompt": "a dog"},
    )

    config = resolve_image_generation_config(task)

    assert config.model == "dall-e-3"
    assert config.api_key is None
    assert config.media_callback is None


def test_resolve_image_generation_config_from_sealed_payload() -> None:
    plain = {
        "prompt": "a cat",
        "model": "flux-pro",
        "api_key": "sk-sealed",
        "chat_id": "chat-sealed",
    }
    sealed = seal_task_payload_secrets(plain)
    task = Task(
        task_id="img-test-sealed",
        task_type="image_generate",
        user_id="user-1",
        status=TaskStatus.PENDING,
        payload=sealed,
    )

    config = resolve_image_generation_config(task)
    assert config.api_key is not None
    assert config.api_key.get_secret_value() == "sk-sealed"
