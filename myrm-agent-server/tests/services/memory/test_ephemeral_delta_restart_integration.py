"""Process-restart simulation: SQLite tail deltas survive in-memory store reset."""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.toolkits.memory.ephemeral_delta.models import (
    DeltaActionKind,
    EphemeralDeltaItem,
)
from myrm_agent_harness.toolkits.memory.ephemeral_delta.shared_store import (
    configure_ephemeral_delta_persistence,
    get_shared_ephemeral_delta_store,
    reset_shared_ephemeral_delta_store_for_tests,
)

from app.services.memory.ephemeral_delta_hydration import (
    ensure_chat_ephemeral_deltas_hydrated,
)


def test_ephemeral_delta_survives_simulated_process_restart(
    tmp_path: Path,
    monkeypatch: object,
) -> None:
    reset_shared_ephemeral_delta_store_for_tests()
    memory_dir = tmp_path / "memory"
    memory_dir.mkdir(parents=True, exist_ok=True)
    db_path = memory_dir / "memory.db"
    chat_id = "chat-restart-sim-01"

    configure_ephemeral_delta_persistence(db_path)
    store = get_shared_ephemeral_delta_store()
    store.record_delta(
        chat_id,
        EphemeralDeltaItem(
            delta_id="delta_restart_sim",
            target_key="profile:nickname",
            content="Sam",
            action=DeltaActionKind.OVERRIDE,
            source="memory_write",
        ),
    )
    assert store.get_active_deltas(chat_id)[0].content == "Sam"

    reset_shared_ephemeral_delta_store_for_tests()

    class _Facade:
        @staticmethod
        def memory_path() -> str:
            return str(memory_dir)

    stub_facade = type(
        "_StubFacade",
        (),
        {"from_state_dir": staticmethod(lambda *_a, **_k: _Facade())},
    )
    monkeypatch.setattr(
        "myrm_agent_harness.toolkits.context_bundle.ContextBundleFacade",
        stub_facade,
    )

    class _Settings:
        class _Database:
            state_dir = str(tmp_path)

        database = _Database()

    monkeypatch.setattr("app.config.settings.settings", _Settings())

    ensure_chat_ephemeral_deltas_hydrated(chat_id)
    reloaded = get_shared_ephemeral_delta_store().get_active_deltas(chat_id)
    assert len(reloaded) == 1
    assert reloaded[0].target_key == "profile:nickname"
    assert reloaded[0].content == "Sam"

    reset_shared_ephemeral_delta_store_for_tests()
