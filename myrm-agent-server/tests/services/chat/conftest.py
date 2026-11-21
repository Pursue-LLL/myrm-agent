"""Fixtures shared by the rewind tests of this directory."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture
def rewind_collaborators() -> Iterator[None]:
    """Checkpoints, goals and snapshots are not under test in a rewind; the history and the rows it keeps are."""
    with (
        patch("app.services.chat.chat_turn._ChatTurnMixin._invalidate_checkpoint_after_mutation", new_callable=AsyncMock),
        patch("app.services.chat.chat_turn.snapshot_pre_rewind", new_callable=AsyncMock, return_value=None),
        patch("app.services.chat.chat_turn.cleanup_orphan_snapshots", new_callable=AsyncMock),
        patch(
            "app.services.chat.session_continuity_service.pause_active_goal_for_rewind",
            new_callable=AsyncMock,
            return_value=False,
        ),
    ):
        yield
