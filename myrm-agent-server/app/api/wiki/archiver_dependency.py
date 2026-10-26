"""Request-scoped wiki archiver dependency shared by every wiki router.

[INPUT]
- app.api.dependencies::get_optional_llm_for_user (POS: the user's configured chat model, a dummy when none is set)
- app.api.memory.utils::get_optional_memory_manager (POS: memory manager that feeds the wiki vector store)
- app.services.wiki.vault::get_wiki_archiver (POS: process-scoped archiver cache)

[OUTPUT]
- get_scoped_wiki_archiver: FastAPI dependency returning the archiver bound to the user's model and the requested vault

[POS]
Single provider of the archiver for routes that compile, query or mutate a vault. Routes that only read or write vault
files use ``app.services.wiki.vault.get_wiki_structure`` instead, so no compile worker is ever built without a model.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Query
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.memory import MemoryManager

from app.api.dependencies import get_optional_llm_for_user
from app.api.memory.utils import get_optional_memory_manager
from app.services.wiki import MemoryToWikiArchiver


async def get_scoped_wiki_archiver(
    llm: Annotated[BaseChatModel, Depends(get_optional_llm_for_user)],
    manager: Annotated[MemoryManager | None, Depends(get_optional_memory_manager)],
    agent_id: Annotated[str | None, Query(description="Agent whose wiki vault to use")] = None,
) -> MemoryToWikiArchiver:
    """Get the wiki archiver bound to an agent-scoped vault path."""
    from app.services.wiki.vault import get_wiki_archiver

    return get_wiki_archiver(llm, manager, agent_id=agent_id)
