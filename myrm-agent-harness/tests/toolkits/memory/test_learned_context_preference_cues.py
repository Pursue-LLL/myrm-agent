"""Every preference cue family reaches the learned-context preview as a stored preference type."""

from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.memory.config import MemoryConfig
from myrm_agent_harness.toolkits.memory.manager import MemoryManager
from myrm_agent_harness.toolkits.memory.strategies.preference_stability import (
    CueFamily,
    PreferenceFacet,
    PreferenceLifecycle,
)


@pytest.mark.parametrize(
    ("cue", "stored_type"),
    [
        (CueFamily.EXPLICIT, "explicit"),
        (CueFamily.IMPLICIT, "implicit"),
        (CueFamily.INFERRED, "implicit"),
    ],
)
async def test_cue_family_maps_onto_the_two_stored_preference_types(
    cue: CueFamily,
    stored_type: str,
    mock_relational_store: AsyncMock,
    mock_vector_store: AsyncMock,
    memory_config: MemoryConfig,
) -> None:
    mock_relational_store.list_rules.return_value = []
    facet = PreferenceFacet(
        id="facet-1",
        key="reply_style",
        value="concise",
        cue=cue,
        lifecycle=PreferenceLifecycle.ACTIVE,
        stability=1.0,
    )
    strategy = AsyncMock()
    strategy.get_active_preferences.return_value = [facet]
    manager = MemoryManager(
        memory_config,
        user_id="test_user",
        relational=mock_relational_store,
        vector=mock_vector_store,
        preference_facet_store=AsyncMock(),
    )
    manager._preference_strategy = strategy

    context = await manager.get_learned_context()

    assert [(p["content"], p["type"]) for p in context["learned_preferences"]] == [("concise", stored_type)]
