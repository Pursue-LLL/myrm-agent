"""The lifespan's prebuilt skill steps: the boot reuses the last sync in local mode only, the warm-up reconciles.

[INPUT]
- app.server.lifespan.prebuilt_skills (POS: the boot and warm-up halves of the prebuilt skill sync)
- app.server.lifespan.startup (POS: phase 1b, which runs the boot step)

[OUTPUT]
- Coverage that the boot step asks for reuse in local mode and never in sandbox mode, that it publishes the outcome as
  before, that the warm-up step publishes only a reconciliation that changed something, and that phase 1b runs the step

[POS]
Server tests. Sandbox instances share a control plane's storage conventions and boot rarely, so only a local
installation takes the fast path; the reconciliation it skips runs after the first screen.
"""

from __future__ import annotations

import ast
import inspect
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.core.skills.prebuilt_sync import PrebuiltSyncResult
from app.server.lifespan import prebuilt_skills, startup

_STORAGE = object()


@pytest.fixture
def published(monkeypatch: pytest.MonkeyPatch) -> SimpleNamespace:
    """Capture what a reconciliation's outcome is published to: the update panel's note and the skill enablement."""
    noted: list[int] = []
    ensure = AsyncMock()
    monkeypatch.setattr("app.api.health.update_status.note_prebuilt_sync_result", noted.append)
    monkeypatch.setattr(
        "app.core.skills.store.service.skills_service",
        SimpleNamespace(user_config=SimpleNamespace(ensure_prebuilt_enabled_after_sync=ensure)),
    )
    monkeypatch.setattr("myrm_agent_harness.toolkits.storage.factory.get_storage_provider", lambda: _STORAGE)
    return SimpleNamespace(noted=noted, ensure=ensure)


@pytest.mark.asyncio
@pytest.mark.parametrize("local", [True, False], ids=["local mode", "sandbox mode"])
async def test_boot_step_asks_for_reuse_only_in_local_mode(
    local: bool, monkeypatch: pytest.MonkeyPatch, published: SimpleNamespace
) -> None:
    asked: list[tuple[object, bool]] = []

    async def fake_sync(storage: object, *, reuse_unchanged: bool = False) -> PrebuiltSyncResult:
        asked.append((storage, reuse_unchanged))
        return PrebuiltSyncResult(synced_count=2, skill_ids=("a", "b"))

    monkeypatch.setattr("app.core.skills.prebuilt_sync.sync_prebuilt_seeds", fake_sync)
    monkeypatch.setattr("app.config.deploy_mode.is_local_mode", lambda: local)

    await prebuilt_skills.init_prebuilt_skills()

    assert asked == [(_STORAGE, local)]
    assert published.noted == [2]
    published.ensure.assert_awaited_once_with(["a", "b"])


@pytest.mark.asyncio
async def test_boot_step_without_skills_only_notes_the_outcome(
    monkeypatch: pytest.MonkeyPatch, published: SimpleNamespace
) -> None:
    async def fake_sync(_storage: object, *, reuse_unchanged: bool = False) -> PrebuiltSyncResult:
        return PrebuiltSyncResult(synced_count=0, skill_ids=())

    monkeypatch.setattr("app.core.skills.prebuilt_sync.sync_prebuilt_seeds", fake_sync)

    await prebuilt_skills.init_prebuilt_skills()

    assert published.noted == [0]
    published.ensure.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("result", "noted"),
    [
        (None, []),
        (PrebuiltSyncResult(synced_count=0, skill_ids=("a",)), []),
        (PrebuiltSyncResult(synced_count=1, skill_ids=("a", "b")), [1]),
    ],
    ids=["nothing was reused", "nothing changed", "a skill was installed"],
)
async def test_warmup_step_publishes_only_a_reconciliation_that_changed_something(
    result: PrebuiltSyncResult | None, noted: list[int], monkeypatch: pytest.MonkeyPatch, published: SimpleNamespace
) -> None:
    async def fake_verify(storage: object) -> PrebuiltSyncResult | None:
        assert storage is _STORAGE
        return result

    monkeypatch.setattr("app.core.skills.prebuilt_sync.verify_reused_sync", fake_verify)

    await prebuilt_skills.verify_prebuilt_skills()

    assert published.noted == noted
    if noted:
        published.ensure.assert_awaited_once_with(list(result.skill_ids) if result else [])
    else:
        published.ensure.assert_not_awaited()


def test_phase_1b_runs_the_boot_step() -> None:
    tree = ast.parse(inspect.getsource(startup._phase_1b_parallel).lstrip())  # noqa: SLF001
    called = {node.func.id for node in ast.walk(tree) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}

    assert "init_prebuilt_skills" in called
