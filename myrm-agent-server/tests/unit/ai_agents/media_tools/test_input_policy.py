"""Tests for the reference-resolution policy shared by the media tools and task executors."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.llms.media_inputs import MediaInputError, resolve_media_inputs

from app.ai_agents.media_tools.input_policy import build_media_input_policy
from app.core.media.reference import MEDIA_SCHEME, read_media_reference

_PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 16


def test_the_policy_reads_media_references_from_the_library_and_downsizes_images() -> None:
    policy = build_media_input_policy()

    assert policy.loaders == {MEDIA_SCHEME: read_media_reference}
    assert policy.image_hook is not None
    assert policy.allowed_roots == ()


def test_the_policy_names_the_workspace_folders_it_may_read() -> None:
    policy = build_media_input_policy(["/work/chat-1", "/work/shared"])

    assert policy.allowed_roots == (Path("/work/chat-1"), Path("/work/shared"))


@pytest.mark.parametrize(("local_mode", "expected"), [(True, True), (False, False)])
def test_only_local_deployments_may_reach_private_networks(local_mode: bool, expected: bool) -> None:
    with patch("app.ai_agents.media_tools.input_policy.is_local_mode", return_value=local_mode):
        assert build_media_input_policy().allow_private_networks is expected


@pytest.mark.asyncio
async def test_a_path_outside_the_workspace_is_refused(tmp_path: Path) -> None:
    outside = tmp_path / "outside" / "secret.png"
    outside.parent.mkdir()
    outside.write_bytes(_PNG)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    with pytest.raises(MediaInputError, match="image_url"):
        await resolve_media_inputs([str(outside)], "image", build_media_input_policy([str(workspace)]), field_name="image_url")


@pytest.mark.asyncio
async def test_a_missing_library_item_names_the_field() -> None:
    with (
        patch("app.ai_agents.media_tools.input_policy.read_media_reference", AsyncMock(side_effect=LookupError("gone"))),
        pytest.raises(MediaInputError, match="reference_images"),
    ):
        await resolve_media_inputs(["media://media_gone"], "image", build_media_input_policy(), field_name="reference_images")
