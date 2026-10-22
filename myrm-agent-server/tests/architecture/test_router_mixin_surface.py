"""Architecture test: the router mixins must keep the methods ``AgentRouter`` composes with.

``AgentRouter`` is built from several mixins by multiple inheritance, and the router executes
turns by calling those methods directly. A module-level function accidentally placed between
two methods silently ends the class body: every later method becomes a nested function, the
mixins still import, and the breakage only shows up when a turn runs.

This pins the methods each mixin must expose, so that mistake fails here instead.
"""

from __future__ import annotations

from app.channels.routing.router import AgentRouter

# Methods the routing loop calls on a live turn. Names come from the composed agent router,
# which is what production instantiates.
_REQUIRED_ROUTER_METHODS = (
    # router_execution.py
    "_resolve_topic",
    "_prepare_execution_context",
    "_execute_prepared_context",
    "_deliver_agent_result",
    "_attach_web_handoff",
    "_register_cleanup",
    # router_stream.py
    "_mark_deferred_placeholder_activity",
    "_resolve_live_placeholder_id",
    # commands/
    "_cancel_active_task",
    "_abort_session_task",
    "_handle_new_session",
)


def test_agent_router_keeps_its_composed_methods() -> None:
    missing = [name for name in _REQUIRED_ROUTER_METHODS if not hasattr(AgentRouter, name)]
    assert missing == [], (
        "AgentRouter lost composed methods — a module-level statement probably ended a mixin "
        "class body early: " + ", ".join(missing)
    )


def test_router_state_key_lives_at_module_level() -> None:
    """The chat lookup helper belongs to the module, not to a mixin's class body."""
    from app.channels.routing import router_execution

    assert callable(router_execution._newest_channel_chat_under)
    assert not hasattr(router_execution.RouterExecutionMixin, "_newest_channel_chat_under")
