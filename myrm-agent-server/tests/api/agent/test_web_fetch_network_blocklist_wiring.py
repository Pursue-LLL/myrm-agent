"""The web fetch tool reads the user's network blocklist from the agent's live security policy on every call.

The agent is pooled across turns and its security policy is reloaded before each one, so a blocklist captured when
the tool was built would keep serving a list the user has already changed. The tool therefore receives a provider
that resolves the policy at call time, the same way the browser tool's domain lists are resolved.
"""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from app.ai_agents.general_agent.tool_setup import ToolSetupMixin


class _Host(ToolSetupMixin):
    """Only the host attributes that ``_setup_search_and_basic_tools`` and the security merge read."""

    locale = "en"
    channel_name = "web_chat"
    enable_web_fetch = True
    fetch_raw_webpage = False
    enable_advanced_retrieval = False
    reranker_config = None
    embedding_config = None
    search_depth = "basic"
    enable_web_search = False
    search_service_cfg = None
    model_cfg = None
    skill_ids = None
    security_config_raw: dict[str, object] | None = None
    agent_security_raw: dict[str, object] | None = None
    declared_capabilities: tuple[str, ...] = ()
    declared_allowed_roots: tuple[str, ...] = ()


def _blocklist_provider(host: _Host) -> Callable[[], tuple[str, ...]]:
    """The provider ``host`` hands to the web fetch tool when its tools are built."""
    with (
        patch("myrm_agent_harness.toolkits.create_web_fetch_tool") as create,
        patch.object(ToolSetupMixin, "_setup_image_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_video_generation_tools"),
        patch.object(ToolSetupMixin, "_setup_tts_tools"),
    ):
        host._setup_search_and_basic_tools([])

    assert create.call_count == 1
    provider = create.call_args.kwargs["network_blocklist_provider"]
    assert callable(provider)
    return provider  # type: ignore[no-any-return]


def test_the_provider_unites_the_users_and_the_agents_blocklists() -> None:
    host = _Host()
    host.security_config_raw = {"networkBlocklist": ["b.example", "A.example"]}
    host.agent_security_raw = {"networkBlocklist": ["*.c.example", "b.example"]}

    assert _blocklist_provider(host)() == ("*.c.example", "a.example", "b.example")


def test_a_blocklist_edited_after_the_tool_was_built_reaches_the_next_call() -> None:
    host = _Host()
    host.security_config_raw = {"networkBlocklist": ["old.example"]}
    provider = _blocklist_provider(host)
    assert provider() == ("old.example",)

    # What `sync_wrapper_security_from_store` does to a pooled agent before each stream turn.
    host.security_config_raw = {"networkBlocklist": ["new.example"]}
    assert provider() == ("new.example",)

    host.security_config_raw = {}
    assert provider() == ()


def test_without_any_blocklist_the_provider_yields_an_empty_tuple() -> None:
    assert _blocklist_provider(_Host())() == ()
