"""Ephemeral delta hydration before agent turns."""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory.ephemeral_delta.models import (
    DeltaActionKind,
    EphemeralDeltaItem,
)
from myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store import (
    reset_shared_ephemeral_delta_store_for_tests,
)

from app.services.memory.ephemeral_delta_hydration import (
    ensure_chat_ephemeral_deltas_hydrated,
)


def test_ensure_chat_ephemeral_deltas_hydrated_loads_volume_rows(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    reset_shared_ephemeral_delta_store_for_tests()
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    db_path = memory_dir / "memory.db"

    from myrm_agent_harness.toolkits.memory.ephemeral_delta.sqlite_persistence import (
        EphemeralDeltaSqlitePersistence,
    )

    persistence = EphemeralDeltaSqlitePersistence(db_path)
    chat_id = "chat-hydrate-1"
    persistence.append_delta(
        chat_id,
        EphemeralDeltaItem(
            delta_id="delta_h1",
            target_key="profile:name",
            content="Alex",
            action=DeltaActionKind.OVERRIDE,
        ),
    )

    class _Facade:
        @staticmethod
        def memory_path() -> str:
            return str(memory_dir)

    class _Settings:
        class _Database:
            state_dir = str(tmp_path)

        database = _Database()

    stub_facade = type(
        "_StubFacade",
        (),
        {"from_state_dir": staticmethod(lambda *_a, **_k: _Facade())},
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.context_bundle.ContextBundleFacade",
        stub_facade,
    )
    monkeypatch.setattr("app.config.settings.settings", _Settings())

    ensure_chat_ephemeral_deltas_hydrated(chat_id)

    from myrm_agent_harness.toolkits.memory.ephemeral_delta import (
        get_shared_ephemeral_delta_store,
    )

    active = get_shared_ephemeral_delta_store().get_active_deltas(chat_id)
    assert len(active) == 1
    assert active[0].content == "Alex"
    reset_shared_ephemeral_delta_store_for_tests()
