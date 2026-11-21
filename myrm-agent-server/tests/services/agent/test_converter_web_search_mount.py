"""Whether a web turn mounts web search: the saved search configuration and the agent profile decide, no live probe does.

[INPUT]
- app/services/agent/params/converter.py (POS: source under inspection; carries the mount decision into the params)
- app/services/agent/params/conversion/sources.py (POS: resolves the search configuration without contacting the provider)
- app/services/agent/params/conversion/tool_surface.py (POS: decides whether web search is mounted for the entry surface)

[OUTPUT]
- Tests that the converter and the source stage never await the readiness probe, and that ``enable_web_search`` is true
  for a fast turn and for an agent turn whose profile carries ``web_search`` when a search service is configured,
  false for an agent turn whose profile does not carry it, and false everywhere when no search service is configured.

[POS]
The built-in tools panel stores the unchecked ``web_search`` as an absent entry in the profile. Mounting follows that
entry whether or not the provider happens to answer a probe, so the choice does not change with the provider's health.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Iterator
from contextlib import contextmanager
from unittest.mock import AsyncMock, patch

import pytest

from app.core.channel_bridge.config_loader import UserConfigs
from app.services.agent.params.conversion import resolve_config_sources
from app.services.agent.params.converter import convert_to_general_agent_params
from app.services.agent.params.models import AgentRequest
from app.services.agent.profile.profile_resolver import ResolvedAgentProfile
from tests.api.agent.conftest import _build_mock_user_configs
from tests.api.agent.utils import get_model_selection

_PROBE_TARGET = "app.services.integrations.search_verify.verify_search_config_cached"


def _request(action_mode: str, tools: tuple[str, ...] = ("web_search",)) -> AgentRequest:
    """A web message with the saved profile's built-in tools as the client sends them in ``agent_config``."""
    return AgentRequest.model_validate(
        {
            "message_id": "m-web-search-mount",
            "chat_id": "c-web-search-mount",
            "query": "hello",
            "model_selection": get_model_selection(),
            "action_mode": action_mode,
            "agent_id": "builtin-developer",
            "agent_config": {
                "skill_ids": [],
                "skill_configs": {},
                "enabled_builtin_tools": list(tools),
                "auto_restore_domains": [],
                "orchestration_mode": "standard",
            },
        }
    )


def _configs(*, search_configured: bool) -> UserConfigs:
    configs = _build_mock_user_configs()
    if search_configured:
        return configs
    return dataclasses.replace(configs, search_cfg=None, search_is_user_configured=False)


@contextmanager
def _converter_env(tools: tuple[str, ...], configs: UserConfigs) -> Iterator[AsyncMock]:
    """The saved profile and the user configs; yields the readiness probe, which fails the test when awaited."""
    profile = ResolvedAgentProfile(
        agent_id="builtin-developer",
        skill_ids=(),
        mcp_ids=(),
        enabled_builtin_tools=tools,
        system_prompt="persona",
        auto_restore_domains=(),
        engine_params={},
    )
    resolver = AsyncMock()
    resolver.resolve = AsyncMock(return_value=profile)
    probe = AsyncMock(side_effect=AssertionError("the web conversion must not probe the search service"))
    with (
        patch("app.services.agent.profile.profile_resolver.get_agent_profile_resolver", return_value=resolver),
        patch("app.core.channel_bridge.config_loader.load_user_configs", AsyncMock(return_value=configs)),
        patch(_PROBE_TARGET, probe),
    ):
        yield probe


@pytest.mark.parametrize(
    ("action_mode", "tools", "search_configured", "mounted"),
    [
        pytest.param("agent", ("web_search",), True, True, id="agent-profile-with-web_search"),
        pytest.param("agent", ("memory",), True, False, id="agent-profile-without-web_search"),
        pytest.param("fast", ("web_search",), True, True, id="fast-profile-with-web_search"),
        pytest.param("fast", ("memory",), True, True, id="fast-profile-without-web_search"),
        pytest.param("agent", ("web_search",), False, False, id="agent-profile-with-web_search-no-service"),
        pytest.param("agent", ("memory",), False, False, id="agent-profile-without-web_search-no-service"),
        pytest.param("fast", ("web_search",), False, False, id="fast-profile-with-web_search-no-service"),
        pytest.param("fast", ("memory",), False, False, id="fast-profile-without-web_search-no-service"),
    ],
)
async def test_the_profile_and_the_search_configuration_decide_whether_web_search_is_mounted(
    action_mode: str,
    tools: tuple[str, ...],
    search_configured: bool,
    mounted: bool,
) -> None:
    configs = _configs(search_configured=search_configured)

    with _converter_env(tools, configs) as probe:
        params, *_ = await convert_to_general_agent_params(_request(action_mode, tools), [])

    # Booleans only: a failed assertion on the config object itself would print the search credential.
    has_search_cfg = params.search_service_cfg is not None
    assert params.enable_web_search is mounted
    assert has_search_cfg is search_configured
    assert probe.await_count == 0


async def test_resolving_the_sources_does_not_contact_the_search_service() -> None:
    configs = _configs(search_configured=True)
    assert configs.search_is_user_configured

    with _converter_env(("web_search",), configs) as probe:
        sources = await resolve_config_sources(_request("agent"), configs)

    has_search_cfg = sources.search_cfg is not None
    assert has_search_cfg
    assert sources.search_is_user_configured
    assert probe.await_count == 0
