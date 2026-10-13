"""Memory compartment resolution for channel turns."""

from __future__ import annotations

import pytest
from myrm_agent_harness.toolkits.memory.config import (
    AgentMemoryPolicy,
    MemoryScopeLevel,
    MemoryWritePolicy,
)

from app.channels.routing.identity_scope import (
    TurnMemoryScope,
    is_untrusted_sender,
    resolve_team_identity,
    resolve_turn_memory_scope,
)
from app.channels.types import IdentityScopeMode, InboundMessage, TopicContext

_PROFILE_POLICY = AgentMemoryPolicy(
    read_scopes=(MemoryScopeLevel.GLOBAL, MemoryScopeLevel.AGENT),
    write_policy=MemoryWritePolicy.AGENT,
    allow_l3_extraction=True,
)


def _msg(*, is_group: bool, **overrides: object) -> InboundMessage:
    base: dict[str, object] = {
        "channel": "feishu",
        "sender_id": "u1",
        "content": "hi",
        "chat_id": "chat9" if is_group else None,
        "is_group": is_group,
    }
    base.update(overrides)
    return InboundMessage(**base)  # type: ignore[arg-type]


def _scope(
    msg: InboundMessage,
    *,
    topic: TopicContext | None = None,
    untrusted: bool = False,
    profile_policy: AgentMemoryPolicy | None = None,
) -> TurnMemoryScope:
    return resolve_turn_memory_scope(
        msg,
        resolve_team_identity(topic, msg),
        untrusted=untrusted,
        profile_policy=profile_policy,
    )


def test_is_untrusted_sender_recognises_guests_and_paired_members() -> None:
    msg = _msg(is_group=False)

    assert is_untrusted_sender("guest_telegram_42", msg)
    assert is_untrusted_sender("paired_member_telegram_42", msg)
    assert not is_untrusted_sender("sandbox", msg)
    assert not is_untrusted_sender("", msg)


def test_is_untrusted_sender_honours_group_guest_turn_metadata() -> None:
    assert is_untrusted_sender("sandbox", _msg(is_group=True, metadata={"guest_turn": "1"}))
    assert not is_untrusted_sender("sandbox", _msg(is_group=True, metadata={"locale": "en"}))


def test_owner_dm_keeps_profile_policy_and_owner_memory() -> None:
    scope = _scope(_msg(is_group=False), profile_policy=_PROFILE_POLICY)

    assert scope == TurnMemoryScope(policy=_PROFILE_POLICY, extra_namespaces=(), is_compartment=False)


def test_owner_dm_without_profile_policy_stays_unbound() -> None:
    scope = _scope(_msg(is_group=False))

    assert (scope.policy, scope.extra_namespaces, scope.is_compartment) == (None, (), False)


def test_bound_group_uses_team_compartment() -> None:
    topic = TopicContext(
        topic_id="chat9",
        agent_id="a1",
        identity_scope=IdentityScopeMode.SHARED,
        identity_id="yifu",
    )

    scope = _scope(_msg(is_group=True), topic=topic)

    assert scope.extra_namespaces == ("ident:yifu",)
    assert scope.is_compartment is True


def test_inherit_bound_group_uses_channel_baseline_compartment() -> None:
    scope = _scope(_msg(is_group=True), topic=TopicContext(topic_id="chat9", agent_id="a1"))

    assert scope.extra_namespaces == ("ident:feishu-baseline",)


def test_unbound_group_gets_stable_per_chat_compartment() -> None:
    scope = _scope(_msg(is_group=True))

    assert scope.extra_namespaces == ("ident:feishu-chat9-channel",)
    assert scope.is_compartment is True


def test_group_compartment_is_independent_of_the_sender() -> None:
    owner_turn = _scope(_msg(is_group=True, sender_id="owner"))
    guest_turn = _scope(_msg(is_group=True, sender_id="guest-7"), untrusted=True)

    assert owner_turn.extra_namespaces == guest_turn.extra_namespaces


def test_group_threads_get_separate_compartments() -> None:
    plain = _scope(_msg(is_group=True))
    threaded = _scope(_msg(is_group=True, thread_id="t1"))

    assert plain.extra_namespaces != threaded.extra_namespaces


def test_untrusted_dm_gets_per_sender_compartment() -> None:
    first = _scope(_msg(is_group=False, sender_id="u1"), untrusted=True)
    second = _scope(_msg(is_group=False, sender_id="u2"), untrusted=True)

    assert first.extra_namespaces == ("ident:feishu-dm-u1-channel",)
    assert first.extra_namespaces != second.extra_namespaces
    assert first.is_compartment is True


def test_untrusted_dm_ignores_bound_topic_identity() -> None:
    topic = TopicContext(
        topic_id="u1",
        agent_id="a1",
        identity_scope=IdentityScopeMode.SHARED,
        identity_id="yifu",
    )

    scope = _scope(_msg(is_group=False), topic=topic, untrusted=True)

    assert scope.extra_namespaces == ("ident:feishu-dm-u1-channel",)


def test_dm_and_group_compartments_never_collide_for_equal_ids() -> None:
    group = _scope(_msg(is_group=True, chat_id="42", sender_id="owner"))
    dm = _scope(_msg(is_group=False, sender_id="42"), untrusted=True)

    assert group.extra_namespaces != dm.extra_namespaces


@pytest.mark.parametrize(
    ("first", "second"),
    [
        ("张三", "李四"),
        ("Alice", "alice"),
        ("+86138", "86138"),
        ("x" * 70 + "a", "x" * 70 + "b"),
    ],
    ids=["non-ascii", "case-only", "stripped-symbol", "truncated-tail"],
)
def test_ids_that_sanitise_alike_never_share_a_compartment(first: str, second: str) -> None:
    dm = [_scope(_msg(is_group=False, sender_id=sender), untrusted=True) for sender in (first, second)]
    group = [_scope(_msg(is_group=True, chat_id=chat)) for chat in (first, second)]

    assert dm[0].extra_namespaces != dm[1].extra_namespaces
    assert group[0].extra_namespaces != group[1].extra_namespaces


def test_compartment_id_is_stable_and_namespace_sized() -> None:
    msg = _msg(is_group=True, chat_id="x" * 200)

    namespace = _scope(msg).extra_namespaces[0]

    assert namespace == _scope(msg).extra_namespaces[0]
    assert len(namespace.removeprefix("ident:")) <= 64


def test_untrusted_dm_compartment_ignores_the_thread() -> None:
    plain = _scope(_msg(is_group=False), untrusted=True)
    threaded = _scope(_msg(is_group=False, thread_id="t1"), untrusted=True)

    assert plain.extra_namespaces == threaded.extra_namespaces


def test_compartment_policy_overrides_profile_policy() -> None:
    scope = _scope(_msg(is_group=True), profile_policy=_PROFILE_POLICY)

    assert scope.policy is not None
    assert scope.policy.read_scopes == (MemoryScopeLevel.CONVERSATION,)
    assert scope.policy.write_policy == MemoryWritePolicy.INHERIT
    assert scope.policy.allow_l3_extraction is False


def test_compartment_always_names_exactly_one_namespace() -> None:
    sparse = _msg(is_group=True, chat_id=None, sender_id="")

    scope = _scope(sparse)

    assert len(scope.extra_namespaces) == 1
    assert scope.extra_namespaces[0].startswith("ident:")
