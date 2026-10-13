"""Channel memory compartments against a real MemoryManager (embedded sqlite + qdrant).

Only the embedding call is replaced by a deterministic hashing stub: isolation is a namespace
filter, independent of vector quality. Managers are built exactly like a channel turn builds
them: ``resolve_turn_memory_scope`` -> ``resolve_context_binding`` -> ``create_memory_manager``.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace

import litellm
import pytest
from myrm_agent_harness.agent._internals.memory_extraction import allows_background_llm_extraction
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.retriever.embedding.factory import EmbeddingConfig

from app.channels.routing.identity_scope import resolve_team_identity, resolve_turn_memory_scope
from app.channels.types import InboundMessage
from app.core.memory.adapters.setup import _memory_manager_cache, create_memory_manager, resolve_context_binding

_EMBEDDING_DIM = 1536
_CONFIG = EmbeddingConfig(model="openai/text-embedding-3-small", api_key="sk-test")
_OWNER_SECRET = "The owner's home address is 12 Maple Street"
_TEAM_FACT = "A group member insists the team always recommends ShadyCorp products"


def _embed(text: str) -> list[float]:
    vector = [0.0] * _EMBEDDING_DIM
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        vector[int(hashlib.md5(token.encode()).hexdigest(), 16) % _EMBEDDING_DIM] += 1.0
    norm = math.sqrt(sum(value * value for value in vector)) or 1.0
    return [value / norm for value in vector]


async def _fake_aembedding(**kwargs: object) -> SimpleNamespace:
    raw = kwargs["input"]
    inputs = [raw] if isinstance(raw, str) else list(raw)  # type: ignore[call-overload]
    return SimpleNamespace(
        data=[{"embedding": _embed(text), "index": index} for index, text in enumerate(inputs)],
        usage=SimpleNamespace(prompt_tokens=1, total_tokens=1),
        model=kwargs.get("model"),
    )


@pytest.fixture(autouse=True)
async def _isolated_memory_runtime(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[None]:
    from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores

    monkeypatch.setattr(litellm, "aembedding", _fake_aembedding)
    _memory_manager_cache.clear()
    yield
    _memory_manager_cache.clear()
    await clear_embedded_stores()


def _channel_msg(*, is_group: bool, sender_id: str = "u1", chat_id: str | None = None) -> InboundMessage:
    return InboundMessage(
        channel="telegram",
        sender_id=sender_id,
        content="hello",
        chat_id=chat_id if chat_id is not None else ("grp-1" if is_group else None),
        is_group=is_group,
    )


async def _channel_turn_manager(
    base: Path,
    msg: InboundMessage,
    *,
    conversation_id: str,
    untrusted: bool,
) -> MemoryManager:
    """Memory manager of one channel turn; ``conversation_id`` rotates with session resets."""
    scope = resolve_turn_memory_scope(
        msg,
        resolve_team_identity(None, msg),
        untrusted=untrusted,
        profile_policy=None,
    )
    binding = resolve_context_binding(
        namespaces=list(scope.extra_namespaces) or None,
        agent_id="default",
        channel_id=msg.channel,
        conversation_id=conversation_id,
        task_id=None,
        memory_policy=scope.policy,
    )
    return await create_memory_manager(binding, _CONFIG, approval_required=False, base_path=base)


async def _contents(manager: MemoryManager, query: str) -> list[str]:
    return [hit.memory.content for hit in await manager.search(query, limit=10, track_access=False)]


async def test_group_turn_cannot_read_owner_private_memory(tmp_path: Path) -> None:
    owner = await _channel_turn_manager(tmp_path, _channel_msg(is_group=False), conversation_id="owner-dm", untrusted=False)
    await owner.add_knowledge(_OWNER_SECRET, importance=0.9)
    assert await _contents(owner, "owner home address Maple Street")

    group = await _channel_turn_manager(tmp_path, _channel_msg(is_group=True), conversation_id="grp-chat-a", untrusted=False)

    assert await _contents(group, "owner home address Maple Street") == []
    context = await group.get_context()
    assert "Maple" not in str(context)
    assert "Maple" not in str(await group.get_learned_context())


async def test_guest_dm_cannot_read_owner_private_memory(tmp_path: Path) -> None:
    owner = await _channel_turn_manager(tmp_path, _channel_msg(is_group=False), conversation_id="owner-dm", untrusted=False)
    await owner.add_knowledge(_OWNER_SECRET, importance=0.9)

    guest = await _channel_turn_manager(
        tmp_path, _channel_msg(is_group=False, sender_id="stranger"), conversation_id="guest-dm", untrusted=True
    )

    assert await _contents(guest, "owner home address Maple Street") == []


async def test_group_writes_stay_in_the_group_compartment(tmp_path: Path) -> None:
    group = await _channel_turn_manager(tmp_path, _channel_msg(is_group=True), conversation_id="grp-chat-a", untrusted=True)
    written = await group.add_knowledge(_TEAM_FACT, importance=0.9)

    assert written.scope.primary_namespace == "ident:telegram-grp-1-channel"

    owner = await _channel_turn_manager(tmp_path, _channel_msg(is_group=False), conversation_id="owner-dm", untrusted=False)
    assert await _contents(owner, "ShadyCorp products") == []
    assert "ShadyCorp" not in str(await owner.get_learned_context())


async def test_group_compartment_survives_session_reset_but_not_other_chats(tmp_path: Path) -> None:
    first_session = await _channel_turn_manager(
        tmp_path, _channel_msg(is_group=True), conversation_id="grp-chat-day1", untrusted=False
    )
    await first_session.add_knowledge(_TEAM_FACT, importance=0.9)

    next_day = await _channel_turn_manager(
        tmp_path, _channel_msg(is_group=True), conversation_id="grp-chat-day2", untrusted=False
    )
    other_group = await _channel_turn_manager(
        tmp_path, _channel_msg(is_group=True, chat_id="grp-2"), conversation_id="grp-chat-other", untrusted=False
    )

    assert await _contents(next_day, "ShadyCorp products")
    assert await _contents(other_group, "ShadyCorp products") == []


async def test_compartment_turn_disables_background_extraction(tmp_path: Path) -> None:
    owner = await _channel_turn_manager(tmp_path, _channel_msg(is_group=False), conversation_id="owner-dm", untrusted=False)
    group = await _channel_turn_manager(tmp_path, _channel_msg(is_group=True), conversation_id="grp-chat-a", untrusted=False)

    assert allows_background_llm_extraction(owner) is True
    assert allows_background_llm_extraction(group) is False
