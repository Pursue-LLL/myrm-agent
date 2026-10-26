"""Startup recovery of interrupted memory-import rollbacks.

[INPUT]
app.server.warmup::_recover_incomplete_memory_import_rollbacks (POS: startup task that resumes journaled rollbacks)

[OUTPUT]
Recovery runs on an install without an embedding model (keyword mode) and is skipped, not failed,
when the platform settings cannot be loaded at all.

[POS]
Contract of the startup memory-import recovery step: embedding is optional, unreadable settings
only skip the step (a warning), never an ERROR-level failed warmup task.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.server.warmup import _recover_incomplete_memory_import_rollbacks


def _session_factory() -> MagicMock:
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=MagicMock())
    session_cm.__aexit__ = AsyncMock(return_value=False)
    return MagicMock(return_value=session_cm)


@pytest.mark.asyncio
async def test_recovery_runs_in_keyword_mode_without_an_embedding() -> None:
    service = MagicMock()
    service.recover_incomplete_rollbacks = AsyncMock(return_value=0)
    create = AsyncMock(return_value=MagicMock())

    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(return_value=(None, None)),
        ),
        patch("app.core.memory.adapters.setup.create_memory_manager", new=create),
        patch("app.platform_utils.get_session_factory", return_value=_session_factory()),
        patch("app.services.memory.imports.import_sessions.MemoryImportSessionService", return_value=service),
    ):
        await _recover_incomplete_memory_import_rollbacks()

    assert create.await_args.args[1] is None
    service.recover_incomplete_rollbacks.assert_awaited_once()


@pytest.mark.asyncio
async def test_unreadable_settings_skip_the_step_instead_of_failing_warmup() -> None:
    create = AsyncMock()

    with (
        patch(
            "app.services.agent.platform_config.load_platform_retrieval_configs",
            new=AsyncMock(side_effect=RuntimeError("no default model configured")),
        ),
        patch("app.core.memory.adapters.setup.create_memory_manager", new=create),
    ):
        await _recover_incomplete_memory_import_rollbacks()

    create.assert_not_awaited()
