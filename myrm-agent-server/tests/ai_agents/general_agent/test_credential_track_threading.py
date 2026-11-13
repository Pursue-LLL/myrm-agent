"""The credential track of a turn reaches the skill backend that decides which skills the agent is offered.

Params choose the track, the factory hands it to the agent, and the agent builds its skill backend for that track; a hop
that dropped it would list the owner's credential-gated skills on a turn that holds none of the owner's credentials.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.security import CredentialTrack

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.ai_agents.general_agent.factory.skills import load_skill_runtime
from app.core.types.business import ModelConfig

_TRACKS = [CredentialTrack.PERSONAL, CredentialTrack.SHARED]
_MODEL = ModelConfig(model="test-model", api_key="test-key")


@pytest.mark.parametrize("track", _TRACKS, ids=lambda track: track.value)
def test_the_agent_runs_on_the_track_its_params_chose(track: CredentialTrack) -> None:
    params = GeneralAgentParams(query="hi", model_cfg=_MODEL, credential_track=track)

    assert AgentFactory.create_general_agent(params).credential_track is track


def test_params_that_name_no_track_run_on_the_personal_one() -> None:
    params = GeneralAgentParams(query="hi", model_cfg=_MODEL)

    assert AgentFactory.create_general_agent(params).credential_track is CredentialTrack.PERSONAL


@pytest.mark.asyncio
@pytest.mark.parametrize("track", _TRACKS, ids=lambda track: track.value)
async def test_the_skill_backend_is_built_for_the_agents_track(track: CredentialTrack) -> None:
    agent = AgentFactory.create_general_agent(GeneralAgentParams(query="hi", model_cfg=_MODEL, credential_track=track))
    create_skill_backend = AsyncMock(return_value=MagicMock())
    user_skill_config = MagicMock()
    user_skill_config.get_config = AsyncMock(return_value=MagicMock(enabled_prebuilt_ids=[]))

    with (
        patch("app.core.skills.loader.create_skill_backend", create_skill_backend),
        patch("app.core.skills.effective_skill_ids.resolve_runtime_skill_ids", AsyncMock(return_value=[])),
        patch("app.core.skills.store.user_config.UserSkillConfigManager", return_value=user_skill_config),
        patch("app.platform_utils.get_storage_provider", return_value=MagicMock()),
    ):
        await load_skill_runtime(agent, "user-1", None)

    assert create_skill_backend.await_args.kwargs["credential_track"] is track
