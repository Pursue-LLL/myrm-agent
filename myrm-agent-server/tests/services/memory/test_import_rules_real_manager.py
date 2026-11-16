"""A confirmed import stores every rule its review counted, on a real memory manager.

[INPUT]
app.services.memory.imports.import_sessions::MemoryImportSessionService (dry-run, then confirm)

[OUTPUT]
Per channel (PLUR store, pasted text, model-extracted paste): the rules the preview maps are the rules the store
holds and the rules the prompt loads.

[POS]
The session tests run on a fake manager that counts every entry as imported. ``MemoryManager.import_memories``
parses each rule with ``ProceduralMemory`` and drops the one without a trigger or an action, so only a real manager
shows a rule that is previewed as mapped and then never stored.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType, ProceduralMemory
from myrm_agent_harness.toolkits.vector.qdrant.factory import clear_embedded_stores
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base
from app.services.memory.imports.import_adapter_utils import DEFAULT_RULE_TRIGGER
from app.services.memory.imports.import_adapters import RequestedImportSource
from app.services.memory.imports.import_sessions import MemoryImportSessionService
from tests.support.offline_memory import offline_memory_manager

pytestmark = pytest.mark.integration

_RULE = "Always run the tests before you merge"
_FACT = "The API lives in app/api"

_PLUR_STORE = f"""
engrams:
  - id: ENG-1
    statement: "{_RULE}"
    type: behavioral
    status: active
    scope: global
    domain: backend
  - id: ENG-2
    statement: "{_FACT}"
    type: architectural
    status: active
    scope: global
    domain: repo
"""

_PASTED_TEXT = f"## Rules\n- {_RULE}\n## Facts\n- {_FACT}\n"

_MODEL_ITEMS = [
    {"content": _RULE, "bucket": "procedural", "trigger": "Before merging a change", "importance": 0.8},
    {"content": _FACT, "bucket": "semantic", "importance": 0.6},
]

# (payload, requested source, the trigger the stored rule must carry)
CHANNELS = [
    pytest.param({"_source": "plur", "raw_yaml": _PLUR_STORE}, "plur", DEFAULT_RULE_TRIGGER, id="plur"),
    pytest.param({"_source": "pasted_memory", "text": _PASTED_TEXT}, "pasted_memory", DEFAULT_RULE_TRIGGER, id="pasted"),
    pytest.param(
        {"_source": "pasted_memory", "text": _PASTED_TEXT, "_model_items": _MODEL_ITEMS},
        "pasted_memory",
        "Before merging a change",
        id="pasted_model",
    ),
]


@pytest.fixture(autouse=True)
async def _reset_embedded_stores() -> AsyncIterator[None]:
    """Release the embedded Qdrant singletons that real managers create between cases."""
    await clear_embedded_stores()
    yield
    await clear_embedded_stores()


@pytest.fixture
async def db_session() -> AsyncIterator[AsyncSession]:
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session
    await engine.dispose()


async def _prompt_rules(manager: MemoryManager) -> list[tuple[object, object]]:
    """(trigger, action) of each rule the prompt's rule block is built from."""
    rules = (await manager.get_context(include_profile=False))["rules"]
    assert isinstance(rules, list)
    return [(rule["trigger"], rule["action"]) for rule in rules if isinstance(rule, dict)]


@pytest.mark.parametrize(("payload", "source", "trigger"), CHANNELS)
async def test_a_confirmed_import_stores_every_mapped_rule_until_it_is_rolled_back(
    payload: dict[str, object],
    source: RequestedImportSource,
    trigger: str,
    db_session: AsyncSession,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async with offline_memory_manager(tmp_path / "memory", monkeypatch) as manager:
        service = MemoryImportSessionService(db_session)
        dry_run_id, preview, _payload_hash, _expires_at = await service.create_dry_run(payload, source)

        confirm = await service.confirm_import(dry_run_id=dry_run_id, manager=manager)

        assert confirm.total_imported == preview.summary.mapped_items == 2
        stored = await manager.list_memories(MemoryType.PROCEDURAL, limit=50)
        assert [(rule.trigger, rule.action) for rule in stored if isinstance(rule, ProceduralMemory)] == [(trigger, _RULE)]
        assert await _prompt_rules(manager) == [(trigger, _RULE)]

        await service.rollback_import(manager=manager, import_batch_id=confirm.import_batch_id)

        assert await manager.list_memories(MemoryType.PROCEDURAL, limit=50) == []
        assert await _prompt_rules(manager) == []
