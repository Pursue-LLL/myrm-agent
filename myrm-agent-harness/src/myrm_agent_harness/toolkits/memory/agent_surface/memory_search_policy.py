"""Memory search policy and optional server-provided backends.

Framework-level ACL for ``memory_search_tool`` corpus routing. Server binds wiki
and conversation providers; runtime cannot broaden corpora beyond policy flags.

[INPUT]
- toolkits.memory.types (POS: Memory type system)

[OUTPUT]
- MemorySearchPolicy: Runtime ACL flags for wiki/sessions corpora and shared memory write bounds.
- MemorySearchBackends: Optional wiki/sessions providers plus wiki_structure for citation URI parity.
- ConcreteSearchCorpus / MemorySearchCorpus: the searchable corpora, and those plus the ``all`` shorthand.
- enabled_search_corpora: the corpora a policy lets the agent search.
- advertised_search_corpora: the ``corpus`` values the model is offered under a policy.
- resolve_search_corpora: Merge policy flags with requested corpus selection.

[POS]
Framework ACL gate for memory_search_tool corpus expansion beyond memory-only recall, and the one source of which
corpora a policy exposes (tool schema, tool descriptions and the ACL all read it).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.memory.protocols.conversation_search import ConversationSearchProtocol
    from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
    from myrm_agent_harness.toolkits.wiki.core.types import QueryResult

ConcreteSearchCorpus = Literal["memory", "wiki", "sessions"]
MemorySearchCorpus = Literal[ConcreteSearchCorpus, "all"]


@dataclass(frozen=True, slots=True)
class MemorySearchPolicy:
    """Runtime ACL for memory_search_tool corpus selection and memory write bounds."""

    allow_wiki: bool = False
    allow_sessions: bool = False
    allow_shared_write: bool = True


@dataclass(frozen=True, slots=True)
class MemorySearchBackends:
    """Optional backends bound by the application layer."""

    query_wiki: Callable[[str], Awaitable[QueryResult]] | None = None
    wiki_agent_id: str | None = None
    wiki_structure: WikiStructure | None = None
    conversation_provider: ConversationSearchProtocol | None = None


def enabled_search_corpora(policy: MemorySearchPolicy) -> tuple[ConcreteSearchCorpus, ...]:
    """The corpora ``policy`` lets the agent search, memory first."""
    corpora: list[ConcreteSearchCorpus] = ["memory"]
    if policy.allow_wiki:
        corpora.append("wiki")
    if policy.allow_sessions:
        corpora.append("sessions")
    return tuple(corpora)


def advertised_search_corpora(policy: MemorySearchPolicy) -> tuple[MemorySearchCorpus, ...]:
    """The ``corpus`` values offered to the model: the enabled corpora, plus ``all`` once there is a choice to make."""
    enabled = enabled_search_corpora(policy)
    return (*enabled, "all") if len(enabled) > 1 else enabled


_DISABLED_CORPUS_REASONS: dict[ConcreteSearchCorpus, str] = {
    "wiki": "Wiki search is not enabled for this agent.",
    "sessions": "Conversation history search is disabled. Enable it in Memory settings.",
}


def resolve_search_corpora(
    corpus: MemorySearchCorpus,
    policy: MemorySearchPolicy,
) -> tuple[list[MemorySearchCorpus], str | None]:
    """Resolve requested corpus into concrete search targets with ACL enforcement."""
    enabled = enabled_search_corpora(policy)
    if corpus == "all":
        return (list(enabled), None)
    if corpus in enabled:
        return ([corpus], None)
    if corpus in _DISABLED_CORPUS_REASONS:
        return ([], _DISABLED_CORPUS_REASONS[corpus])
    return ([], f"Unknown corpus: {corpus}")
