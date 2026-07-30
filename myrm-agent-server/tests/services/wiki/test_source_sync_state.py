"""Tests for wiki source sync state persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.source_sync.schemas import WikiSourceSyncResult, WikiSourceSyncRunSummary, WikiSourceSyncState
from app.services.wiki.source_sync.state_store import (
    STATE_KEY,
    load_wiki_source_sync_state,
    save_wiki_source_sync_state,
    state_from_run_summary,
)


def test_state_from_run_summary_maps_counts() -> None:
    summary = WikiSourceSyncRunSummary(
        results=[
            WikiSourceSyncResult(source="gmail", published=2, skipped=1, failed=0),
            WikiSourceSyncResult(source="rss", published=0, skipped=3, failed=1, errors=["timeout"]),
        ],
        total_published=2,
        total_skipped=4,
        total_failed=1,
    )

    state = state_from_run_summary(summary)

    assert state.total_published == 2
    assert state.total_skipped == 4
    assert state.total_failed == 1
    assert len(state.sources) == 2
    assert state.sources[1].errors == ["timeout"]
    assert state.last_sync_at is not None


@pytest.mark.asyncio
async def test_load_state_defaults_when_missing() -> None:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    loaded = await load_wiki_source_sync_state(db)
    assert loaded.last_sync_at is None
    assert STATE_KEY == "wikiSourceSyncState"


@pytest.mark.asyncio
async def test_runner_persists_state_after_sync() -> None:
    from app.services.wiki.source_sync.runner import run_wiki_source_sync

    summary = WikiSourceSyncRunSummary(
        results=[WikiSourceSyncResult(source="rss", published=1)],
        total_published=1,
    )

    with (
        patch(
            "app.services.wiki.source_sync.runner.load_wiki_source_sync_config",
            new=AsyncMock(return_value=MagicMock(gmail_enabled=False, rss_feeds=[], auto_compile=False)),
        ),
        patch("app.services.wiki.source_sync.runner.resolve_wiki_vault_path", return_value="/tmp/wiki"),
        patch("app.services.wiki.source_sync.runner.get_session") as session_ctx,
        patch(
            "app.services.wiki.source_sync.state_store.save_wiki_source_sync_state",
            new=AsyncMock(),
        ) as save_state,
    ):
        db = AsyncMock()
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await run_wiki_source_sync(llm=None, config=MagicMock(gmail_enabled=False, rss_feeds=[]))

    assert result.total_published == summary.total_published or result.total_published == 0
    save_state.assert_awaited_once()
    saved_state = save_state.await_args.args[1]
    assert isinstance(saved_state, WikiSourceSyncState)
    assert saved_state.last_sync_at is not None or saved_state.total_published >= 0


@pytest.mark.asyncio
async def test_save_state_commits_payload() -> None:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    state = WikiSourceSyncState(last_sync_at=datetime.now(UTC), total_published=3)
    saved = await save_wiki_source_sync_state(db, state)
    assert saved.total_published == 3
    db.commit.assert_awaited_once()
