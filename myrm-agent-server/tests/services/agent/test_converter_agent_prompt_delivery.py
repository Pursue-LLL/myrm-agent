"""Web agent-mode request shape through the converter: how the saved agent persona reaches ``user_instructions``.

[INPUT]
- app/services/agent/params/conversion/profile_apply.py (POS: source under inspection; merges the saved persona into the instructions)
- app/services/agent/params/models.py (POS: AgentRequest / AgentConfigRequest request DTOs)

[OUTPUT]
- Tests that the saved persona follows the client's instructions, that a chat-level ``agent_config.system_prompt`` replaces it,
  that an empty one clears it, that it still applies when the saved agent is gone, and that a request without
  ``agent_config`` keeps the saved persona.

[POS]
The web client sends ``agent_config`` with every agent-mode message. The fixtures carry it, so the branch real traffic takes
is the one under test.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection

_PERSONA = "Saved persona: always answer in rhyme."
_GLOBAL_INSTRUCTION = "Global instruction: be concise."
_OVERRIDE = "Chat-level persona: answer like a pirate."

_WEB_AGENT_CONFIG: dict[str, object] = {
    "skill_ids": [],
    "skill_configs": {},
    "enabled_builtin_tools": ["web_search"],
    "auto_restore_domains": [],
    "orchestration_mode": "standard",
}


def _request(*, agent_config: dict[str, object] | None) -> AgentRequest:
    """The first agent-mode message of the web client: agent id, the client's instructions, and (usually) agent_config."""
    body: dict[str, object] = {
        "message_id": "m-prompt-delivery",
        "chat_id": "c-prompt-delivery",
        "query": "hello",
        "model_selection": get_model_selection(),
        "action_mode": "agent",
        "agent_id": "builtin-developer",
        "user_instructions": _GLOBAL_INSTRUCTION,
    }
    if agent_config is not None:
        body["agent_config"] = agent_config
    return AgentRequest.model_validate(body)


@contextmanager
def _converter_env(*, agent_exists: bool) -> Iterator[None]:
    """Everything the converter reads from outside: the saved profile, the user configs, the live search probe."""
    profile = ResolvedAgentProfile(
        agent_id="builtin-developer",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=("web_search",),
        system_prompt=_PERSONA,
        auto_restore_domains=(),
        engine_params={},
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=profile if agent_exists else None)
    with (
        patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=resolver),
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=_build_mock_user_configs())),
        patch("app.services.integrations.search_verify.verify_search_config_cached", AsyncMock(return_value=True)),
    ):
        yield


async def _instructions(request: AgentRequest, *, agent_exists: bool = True) -> str:
    with _converter_env(agent_exists=agent_exists):
        params, *_ = await convert_to_general_agent_params(request, [])
    assert params.user_instructions is not None
    return params.user_instructions


async def test_saved_persona_follows_the_clients_instructions() -> None:
    text = await _instructions(_request(agent_config=_WEB_AGENT_CONFIG))

    assert text.count(_PERSONA) == 1
    assert text.index(_GLOBAL_INSTRUCTION) < text.index(_PERSONA)


async def test_a_chat_level_prompt_replaces_the_saved_persona() -> None:
    text = await _instructions(_request(agent_config={**_WEB_AGENT_CONFIG, "system_prompt": _OVERRIDE}))

    assert text.count(_OVERRIDE) == 1
    assert _PERSONA not in text
    assert text.index(_GLOBAL_INSTRUCTION) < text.index(_OVERRIDE)


async def test_an_empty_chat_level_prompt_clears_the_persona() -> None:
    text = await _instructions(_request(agent_config={**_WEB_AGENT_CONFIG, "system_prompt": ""}))

    assert _PERSONA not in text
    assert _GLOBAL_INSTRUCTION in text


async def test_a_chat_level_prompt_survives_a_deleted_agent() -> None:
    """The chat-level text exists only in the request; losing the saved agent must not make it vanish."""
    text = await _instructions(
        _request(agent_config={**_WEB_AGENT_CONFIG, "system_prompt": _OVERRIDE}),
        agent_exists=False,
    )

    assert text.count(_OVERRIDE) == 1
    assert _PERSONA not in text
    assert text.index(_GLOBAL_INSTRUCTION) < text.index(_OVERRIDE)


async def test_a_request_without_agent_config_keeps_the_saved_persona() -> None:
    text = await _instructions(_request(agent_config=None))

    assert text.count(_PERSONA) == 1
    assert text.index(_GLOBAL_INSTRUCTION) < text.index(_PERSONA)
