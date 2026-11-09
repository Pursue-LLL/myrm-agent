"""A query names a stored exact identifier only when it writes that identifier whole.

Containment is not naming: a stored port ``22`` is not named by a query about ``2022``, nor ``10.0.0.5`` by
``10.0.0.55``. The matrix pins the rule on the classifier itself, and the retriever cases show both ranking
pipelines apply it, so an unrelated exact fact never takes the top slot.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.memory.retriever import MemoryRetriever
from myrm_agent_harness.toolkits.memory.strategies.exact_fact import ExactFactClassifier
from myrm_agent_harness.toolkits.memory.types import MemorySearchResult, MemoryType, SemanticMemory

SSH = "The ssh service listens on port 22"
GATEWAY = "The gateway is at 10.0.0.5:8080"


def names(stored: str, query: str) -> bool:
    identifiers = ExactFactClassifier.extract_identifiers(stored)
    return ExactFactClassifier.mentions_any(identifiers, ExactFactClassifier.query_keys(query))


@pytest.mark.parametrize(
    ("stored", "query"),
    [
        (SSH, "which service uses port 22?"),
        (SSH, "ssh on 22/tcp"),
        (SSH, "端口：22 是什么服务"),
        (SSH, "what is on 10.0.0.5:22"),
        (GATEWAY, "gateway 10.0.0.5:8080?"),
        (GATEWAY, "访问http://10.0.0.5:8080/api"),
        ("Dev server runs at localhost:3000", "what runs on localhost:3000"),
        ("The dev server listens on port 3000", "what is on localhost:3000"),
        ("Release v1.2.3 is the stable line", "which release is 1.2.3"),
        ("Release 1.2.3 is the stable line", "what about v1.2.3."),
        ("Set MAX_RETRY to three", "what does max_retry=3 do"),
        ("Order 123e4567-e89b-12d3-a456-426614174000 shipped", "status of 123E4567-E89B-12D3-A456-426614174000"),
    ],
)
def test_a_query_that_writes_the_identifier_names_it(stored: str, query: str) -> None:
    assert names(stored, query)


@pytest.mark.parametrize(
    ("stored", "query"),
    [
        (SSH, "what did we ship in 2022"),
        (SSH, "the meeting on 2026-05-22 moved"),
        (SSH, "it took 12:22 to finish"),
        ("The web app runs on port 8080", "is anything listening on port 18080"),
        (GATEWAY, "what is the gateway 10.0.0.55:8080"),
        (GATEWAY, "what is the gateway 10.0.0.9:8080"),
        ("The gateway is at 10.0.0.5", "what is at 10.0.0.55"),
        ("Release v1.2.3 is the stable line", "what changed in v1.2.30"),
        ("Release v1.2.3 is the stable line", "what changed in v1.2.3-rc1"),
        ("Set MAX_RETRY to three", "what does MAX_RETRY_COUNT control"),
        ("The web app runs on port 80", "retries in v80 builds"),
    ],
)
def test_a_query_that_merely_contains_the_identifier_does_not_name_it(stored: str, query: str) -> None:
    assert not names(stored, query)


def candidates(stored: str) -> list[MemorySearchResult]:
    """The exact fact ranked last behind plain memories that use the same words, so only a boost can lift it."""
    exact = SemanticMemory(
        id="exact",
        content=stored,
        is_exact_fact=True,
        exact_identifiers=ExactFactClassifier.extract_identifiers(stored),
    )
    plain = [SemanticMemory(id=f"plain-{index}", content=f"{stored} (note {index})") for index in range(4)]
    return [MemorySearchResult(memory=memory, score=0.9, memory_type=MemoryType.SEMANTIC) for memory in (*plain, exact)]


def rank_first(stored: str, query: str, pipeline: str) -> str:
    retriever = MemoryRetriever()
    if pipeline == "rank":
        return retriever.rank(candidates(stored), limit=5, query=query)[0].id
    return retriever.fuse([candidates(stored)], limit=5, query=query)[0].id


@pytest.mark.parametrize("pipeline", ["rank", "fuse"])
def test_a_named_exact_fact_takes_the_top_slot(pipeline: str) -> None:
    assert rank_first(SSH, "which service uses port 22?", pipeline) == "exact"


@pytest.mark.parametrize("pipeline", ["rank", "fuse"])
def test_an_unrelated_exact_fact_does_not_take_the_top_slot(pipeline: str) -> None:
    assert rank_first(SSH, "what did we ship in 2022", pipeline) != "exact"
