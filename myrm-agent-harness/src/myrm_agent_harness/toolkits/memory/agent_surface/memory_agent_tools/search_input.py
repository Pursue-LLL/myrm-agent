"""Argument schema of memory_search_tool, derived from the corpus policy.

The model is offered what the policy lets it do and nothing else: ``corpus`` only when there is more than one corpus
to choose from (and then only the enabled ones), the conversation-expansion arguments only when sessions can be
searched. Under a memory-only policy ``corpus`` stays accepted but unadvertised, so a caller that still sends one
reaches the ACL in ``resolve_search_corpora`` and gets its explicit answer instead of a silently different search.

[INPUT]
- toolkits.memory.agent_surface.memory_search_policy (POS: the corpora a policy exposes)
- toolkits.memory.agent_surface.memory_recall_budget::DEFAULT_RECALL_LIMIT (POS: recall limit SSOT)

[OUTPUT]
- memory_search_input: the pydantic args schema of memory_search_tool under a policy

[POS]
Schema half of ``search_tool``: what the model may pass. Which corpora a request reaches is decided by the ACL.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, create_model
from pydantic.json_schema import SkipJsonSchema

from myrm_agent_harness.toolkits.memory.agent_surface.memory_recall_budget import DEFAULT_RECALL_LIMIT
from myrm_agent_harness.toolkits.memory.agent_surface.memory_search_policy import (
    MemorySearchCorpus,
    MemorySearchPolicy,
    advertised_search_corpora,
)


class _SearchArguments(BaseModel):
    """The arguments every policy offers."""

    query: str = ""
    categories: list[str] | str | None = None
    limit: int | str | None = DEFAULT_RECALL_LIMIT
    profile_key: str | None = None
    memory_id: str | None = None
    detail_level: Literal["overview", "full"] = "overview"
    domain: Literal["user", "assistant", "task"] | None = None
    since: str | None = None
    until: str | None = None


class _SessionSearchArguments(_SearchArguments):
    """Adds the conversation expansion, which only a sessions search understands."""

    expand_conversation_id: str | None = None
    expand_message_id: str | None = None
    expand_window: int = 5


class _MemoryOnlyArguments(_SearchArguments):
    """With a single corpus there is nothing to choose; ``corpus`` is accepted but never advertised."""

    corpus: SkipJsonSchema[MemorySearchCorpus] = "memory"


@lru_cache(maxsize=4)
def _input_model(allow_wiki: bool, allow_sessions: bool) -> type[BaseModel]:
    choices = advertised_search_corpora(MemorySearchPolicy(allow_wiki=allow_wiki, allow_sessions=allow_sessions))
    if len(choices) == 1:
        return _MemoryOnlyArguments
    return create_model(
        "MemorySearchInput",
        __base__=_SessionSearchArguments if allow_sessions else _SearchArguments,
        # ``Literal.__getitem__`` builds the enum from the policy's values, which a static ``Literal[...]`` cannot;
        # the checker types its result as ``object``.
        corpus=(Literal.__getitem__(choices), "memory"),  # type: ignore[arg-type]
    )


def memory_search_input(policy: MemorySearchPolicy) -> type[BaseModel]:
    """The args schema memory_search_tool exposes under ``policy``."""
    return _input_model(policy.allow_wiki, policy.allow_sessions)
