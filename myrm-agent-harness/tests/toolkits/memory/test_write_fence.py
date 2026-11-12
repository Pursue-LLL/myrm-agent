"""The write fence: a writer may target its write scope and the broadcast namespaces it reads, and nothing else."""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory._internal.write_fence import within_write_grant, write_grant
from myrm_agent_harness.toolkits.memory.types import MemoryScope


def _scope(*namespaces: str) -> MemoryScope:
    return MemoryScope(primary_namespace=namespaces[0], namespaces=list(namespaces))


def test_the_grant_is_the_write_scope_plus_the_broadcast_namespaces_the_writer_reads() -> None:
    grant = write_grant(_scope("agent:x"), ["global", "agent:x", "agent:y", "project:p", "shared:team"])

    assert grant == {"agent:x", "global", "shared:team"}  # another agent's space and a read-only project stay out


def test_a_broadcast_namespace_the_writer_does_not_read_is_not_granted() -> None:
    assert write_grant(_scope("agent:x"), ["agent:x"]) == {"agent:x"}


def test_a_memory_is_within_the_grant_only_when_every_namespace_of_it_is() -> None:
    grant = frozenset({"agent:x", "global"})

    assert within_write_grant(["agent:x"], grant)
    assert within_write_grant(["global", "agent:x"], grant)
    assert not within_write_grant(["agent:x", "project:p"], grant)


def test_an_empty_grant_fences_nothing() -> None:
    assert within_write_grant(["project:p"], frozenset())
