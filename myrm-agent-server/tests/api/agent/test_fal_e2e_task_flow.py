"""Universal Task Flow E2E Integration: FAL.ai Video Generation & Continuation Lifecycle."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="agents_api")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_fal_video_task_flow_full_lifecycle(client: TestClient) -> None:
    """Validate full 5-step task flow E2E lifecycle for FAL.ai provider & multi-clip continuation."""
    # Step 1: User enters Settings and queries media provider status
    mock_cfgs = {
        "providers": [
            {
                "id": "fal",
                "isEnabled": True,
                "apiKeys": [{"key": "fal-test-secret-key-xyz", "isActive": True}],
            }
        ]
    }
    mock_config_obj = AsyncMock()
    mock_config_obj.providers_dict = mock_cfgs

    with (
        patch(
            "app.core.channel_bridge.config_loader.load_user_configs",
            new_callable=AsyncMock,
            return_value=mock_config_obj,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.video.providers.fal_provider.FalVideoProvider.health_check",
            new_callable=AsyncMock,
            return_value=True,
        ),
    ):
        status_resp = client.get("/api/v1/agents/media-provider-status")
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["success"] is True
        providers = status_data["data"]["providers"]
        assert "fal" in providers
        assert providers["fal"]["hasApiKey"] is True
        assert providers["fal"]["healthy"] is True

        # Step 2: User triggers Doctor connection test for FAL.ai
        test_resp = client.post(
            "/api/v1/agents/test-media-config",
            json={
                "mediaType": "video",
                "provider": "fal",
                "model": "fal-ai/flux-3-video",
            },
        )
        assert test_resp.status_code == 200
        test_data = test_resp.json()
        assert test_data["success"] is True
        assert test_data["data"]["status"] == "ok"

    # Step 3: Verify prebuilt skill flux3-prompting-guide availability
    from pathlib import Path
    from myrm_agent_harness.backends.skills._utils import parse_skill_frontmatter

    server_root = Path(__file__).resolve().parents[3]
    skill_file = server_root / "assets" / "prebuilt_skills" / "flux3-prompting-guide" / "SKILL.md"
    assert skill_file.exists(), "Prebuilt skill flux3-prompting-guide must exist"
    parsed_skill = parse_skill_frontmatter(skill_file.read_text(encoding="utf-8"), "flux3-prompting-guide")
    assert parsed_skill.name == "flux3-prompting-guide"
    assert "video_tool" in parsed_skill.allowed_tools

    # Step 4: Verify Harness level FAL continuation & keyframe synthesis execution
    from myrm_agent_harness.toolkits.llms.video import (
        VideoGenerationConfig,
        VideoAsset,
    )
    from myrm_agent_harness.toolkits.llms.video.providers.fal_provider import FalVideoProvider
    from pydantic import SecretStr

    provider = FalVideoProvider()
    cfg = VideoGenerationConfig(
        provider="fal",
        model="fal-ai/flux-3-video",
        api_key=SecretStr("fal-mock-token"),
        timeout_seconds=30,
    )

    fake_video = b"\x00\x00\x00\x18ftypmp42mock-rendered-clip"
    fake_submit_resp = MagicMock()
    fake_submit_resp.status_code = 200
    fake_submit_resp.json.return_value = {
        "status_url": "https://queue.fal.run/mock-status",
        "response_url": "https://queue.fal.run/mock-result",
        "request_id": "mock-req-001",
    }

    fake_status_resp = MagicMock()
    fake_status_resp.status_code = 200
    fake_status_resp.json.return_value = {"status": "COMPLETED"}

    fake_result_resp = MagicMock()
    fake_result_resp.status_code = 200
    fake_result_resp.json.return_value = {
        "video": {"url": "https://v3.fal.media/mock-video.mp4"}
    }

    mock_dl_resp = MagicMock()
    mock_dl_resp.status_code = 200
    mock_dl_resp.content = fake_video

    with (
        patch("myrm_agent_harness.toolkits.llms.video.providers.fal_provider.create_httpx_client") as mock_client_factory,
        patch("myrm_agent_harness.toolkits.llms.video.providers.fal_provider.secure_get", return_value=mock_dl_resp),
    ):
        mock_http = AsyncMock()
        mock_http.post.return_value = fake_submit_resp
        mock_http.get.side_effect = [fake_status_resp, fake_result_resp]
        mock_client_factory.return_value = mock_http

        # Generate Clip 1: Keyframe mode
        import asyncio
        clip1_output = asyncio.run(
            provider.generate(
                prompt="A stylish hero walking down a neon street, camera tracking back",
                config=cfg,
                reference_images=[b"fake_start_frame", b"fake_end_frame"],
            )
        )
        assert len(clip1_output.assets) == 1
        assert clip1_output.assets[0].data == fake_video

        # Generate Clip 2: Continuation mode (flowing from Clip 1)
        mock_http.get.side_effect = [fake_status_resp, fake_result_resp]
        clip2_output = asyncio.run(
            provider.generate(
                prompt="Hero draws energy orb, camera orbits smoothly, maintaining character facial features",
                config=cfg,
                reference_videos=[clip1_output.assets[0].data],
            )
        )
        assert len(clip2_output.assets) == 1
        assert clip2_output.assets[0].data == fake_video
        assert clip2_output.provider_metadata.get("request_id") == "mock-req-001"
