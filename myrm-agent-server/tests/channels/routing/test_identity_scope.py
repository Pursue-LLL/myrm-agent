"""Team-shared identity scope — parser and resolver contracts."""

import pytest

from app.channels.routing.commands.commands import parse_topic_args
from app.channels.routing.identity_scope import (
    default_identity_id,
    resolve_team_identity,
)
from app.channels.types import IdentityScopeMode, InboundMessage, TopicContext


def _group_msg(**overrides: object) -> InboundMessage:
    base: dict[str, object] = {
        "channel": "feishu",
        "sender_id": "u1",
        "content": "hi",
        "chat_id": "chat9",
        "is_group": True,
        "mentioned": True,
    }
    base.update(overrides)
    return InboundMessage(**base)  # type: ignore[arg-type]


def test_parse_bind_identity_kv() -> None:
    cmd = parse_topic_args("bind", "agent=my-agent identity=义父 identity_scope=shared")
    assert cmd.agent_id == "my-agent"
    assert cmd.identity_name == "义父"
    assert cmd.identity_scope == "shared"


def test_parse_bind_identity_quoted_multiword() -> None:
    cmd = parse_topic_args("bind", 'agent=my-agent identity="Yi Fu" identity_scope=private')
    assert cmd.identity_name == "Yi Fu"
    assert cmd.identity_scope == "private"


def test_parse_bind_identity_tail_never_hijacks_agent() -> None:
    cmd = parse_topic_args("bind", "identity=Yi Fu")
    assert cmd.agent_id is None
    assert cmd.identity_name == "Yi"


def test_parse_bind_legacy_forms_unchanged() -> None:
    assert parse_topic_args("bind", "my-agent").agent_id == "my-agent"
    cmd = parse_topic_args("bind", "workspace=project:123 my-agent")
    assert (cmd.agent_id, cmd.project_id) == ("my-agent", "123")


def test_default_identity_id_stable_and_safe() -> None:
    assert default_identity_id("feishu", "chat9", None) == "feishu-chat9-channel"
    assert default_identity_id("feishu", "chat 9!", "t/1") == "feishu-chat9-t1"


def test_resolve_group_shared_identity() -> None:
    topic = TopicContext(
        topic_id="chat9",
        agent_id="a1",
        identity_scope=IdentityScopeMode.SHARED,
        identity_id="yifu",
        identity_name="义父",
    )
    resolved = resolve_team_identity(topic, _group_msg())
    assert resolved.is_fallback is False
    assert resolved.memory_namespace == "ident:yifu"
    assert resolved.spec.credential_track.value == "shared"


def test_resolve_group_inherit_uses_baseline() -> None:
    topic = TopicContext(topic_id="chat9", agent_id="a1")
    resolved = resolve_team_identity(topic, _group_msg())
    assert resolved.memory_namespace == "ident:feishu-baseline"


def test_resolve_revoked_or_unbound_falls_back() -> None:
    topic = TopicContext(topic_id="chat9", agent_id="a1", identity_revoked=True)
    assert resolve_team_identity(topic, _group_msg()).is_fallback is True
    assert resolve_team_identity(None, _group_msg()).is_fallback is True


def test_resolve_dm_never_shared() -> None:
    topic = TopicContext(
        topic_id="chat9",
        agent_id="a1",
        identity_scope=IdentityScopeMode.SHARED,
        identity_id="yifu",
    )
    resolved = resolve_team_identity(topic, _group_msg(is_group=False, chat_id=None))
    assert resolved.spec.credential_track.value == "personal"
    assert resolved.memory_namespace is None


def test_invalid_scope_rejected_at_bind_layer() -> None:
    from app.channels.types import IdentityScopeMode as Mode

    with pytest.raises(ValueError):
        Mode("bogus")
