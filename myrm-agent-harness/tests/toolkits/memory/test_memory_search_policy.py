"""Tests for memory search policy ACL."""

from typing import get_args

import pytest

from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    ConcreteSearchCorpus,
    MemorySearchPolicy,
    advertised_search_corpora,
    enabled_search_corpora,
    resolve_search_corpora,
)

_POLICY_MATRIX = [
    pytest.param(MemorySearchPolicy(), ("memory",), ("memory",), id="memory-only"),
    pytest.param(MemorySearchPolicy(allow_wiki=True), ("memory", "wiki"), ("memory", "wiki", "all"), id="wiki"),
    pytest.param(
        MemorySearchPolicy(allow_sessions=True), ("memory", "sessions"), ("memory", "sessions", "all"), id="sessions"
    ),
    pytest.param(
        MemorySearchPolicy(allow_wiki=True, allow_sessions=True),
        ("memory", "wiki", "sessions"),
        ("memory", "wiki", "sessions", "all"),
        id="wiki-and-sessions",
    ),
]


def test_resolve_memory_only() -> None:
    corpora, reason = resolve_search_corpora("memory", MemorySearchPolicy())
    assert corpora == ["memory"]
    assert reason is None


def test_resolve_sessions_blocked_by_policy() -> None:
    corpora, reason = resolve_search_corpora("sessions", MemorySearchPolicy(allow_sessions=False))
    assert corpora == []
    assert reason is not None


def test_resolve_all_respects_policy_flags() -> None:
    corpora, reason = resolve_search_corpora(
        "all",
        MemorySearchPolicy(allow_wiki=True, allow_sessions=True),
    )
    assert corpora == ["memory", "wiki", "sessions"]
    assert reason is None


def test_resolve_all_skips_disabled_corpora() -> None:
    corpora, reason = resolve_search_corpora("all", MemorySearchPolicy(allow_wiki=False, allow_sessions=False))
    assert corpora == ["memory"]
    assert reason is None


def test_resolve_web_corpus_unknown() -> None:
    corpora, reason = resolve_search_corpora("web", MemorySearchPolicy())  # type: ignore[arg-type]
    assert corpora == []
    assert reason == "Unknown corpus: web"


def test_resolve_wiki_blocked_by_policy() -> None:
    corpora, reason = resolve_search_corpora("wiki", MemorySearchPolicy(allow_wiki=False))
    assert corpora == []
    assert reason is not None
    assert "Wiki" in reason


def test_resolve_wiki_allowed() -> None:
    corpora, reason = resolve_search_corpora("wiki", MemorySearchPolicy(allow_wiki=True))
    assert corpora == ["wiki"]
    assert reason is None


def test_resolve_sessions_allowed() -> None:
    corpora, reason = resolve_search_corpora("sessions", MemorySearchPolicy(allow_sessions=True))
    assert corpora == ["sessions"]
    assert reason is None


def test_resolve_unknown_corpus() -> None:
    corpora, reason = resolve_search_corpora("bogus", MemorySearchPolicy())  # type: ignore[arg-type]
    assert corpora == []
    assert reason is not None
    assert "Unknown corpus" in reason


def test_memory_search_policy_allow_shared_write_default_true() -> None:
    policy = MemorySearchPolicy()
    assert policy.allow_shared_write is True


def test_memory_search_policy_allow_shared_write_disabled() -> None:
    policy = MemorySearchPolicy(allow_shared_write=False)
    assert policy.allow_shared_write is False


@pytest.mark.parametrize(("policy", "enabled", "advertised"), _POLICY_MATRIX)
def test_enabled_and_advertised_corpora_follow_policy(
    policy: MemorySearchPolicy,
    enabled: tuple[str, ...],
    advertised: tuple[str, ...],
) -> None:
    assert enabled_search_corpora(policy) == enabled
    assert advertised_search_corpora(policy) == advertised


@pytest.mark.parametrize(("policy", "enabled", "advertised"), _POLICY_MATRIX)
def test_acl_accepts_exactly_what_is_advertised(
    policy: MemorySearchPolicy,
    enabled: tuple[str, ...],
    advertised: tuple[str, ...],
) -> None:
    for corpus in advertised:
        _, reason = resolve_search_corpora(corpus, policy)  # type: ignore[arg-type]
        assert reason is None, corpus
    assert resolve_search_corpora("all", policy)[0] == list(enabled)
    for corpus in set(get_args(ConcreteSearchCorpus)) - set(enabled):
        corpora, reason = resolve_search_corpora(corpus, policy)
        assert corpora == []
        assert reason, corpus
