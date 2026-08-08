"""Tests for wiki source sync state persistence."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki.agent_scope import DEFAULT_AGENT_SCOPE
from app.services.wiki.source_sync.schemas import (
    WikiSourceSyncResult,
    WikiSourceSyncRunSummary,
    WikiSourceSyncState,
)
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
            WikiSourceSyncResult(
                source="rss", published=0, skipped=3, failed=1, errors=["timeout"]
            ),
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
async def test_save_state_scoped_by_agent() -> None:
    db = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.first.return_value = None
    db.execute = AsyncMock(return_value=result_mock)

    state = WikiSourceSyncState(last_sync_at=datetime.now(UTC), total_published=3)
    saved = await save_wiki_source_sync_state(db, state, agent_id="agent-42")
    assert saved.total_published == 3
    db.commit.assert_awaited_once()
    added = db.add.call_args.args[0]
    payload = added.config_value
    assert DEFAULT_AGENT_SCOPE in payload["agents"] or "agent-42" in payload["agents"]


@pytest.mark.asyncio
async def test_runner_persists_state_with_agent_scope() -> None:
    from app.services.wiki.source_sync.runner import run_wiki_source_sync
    from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig

    config = WikiSourceSyncConfig(gmail_enabled=False, rss_feeds=[])

    with (
        patch("app.services.wiki.source_sync.runner.get_session") as session_ctx,
        patch(
            "app.services.wiki.source_sync.state_store.save_wiki_source_sync_state",
            new=AsyncMock(),
        ) as save_state,
        patch(
            "app.services.wiki.source_sync.runner.resolve_wiki_vault_path",
            return_value="/tmp/wiki",
        ),
    ):
        db = AsyncMock()
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        await run_wiki_source_sync(llm=None, agent_id="agent-99", config=config)

    save_state.assert_awaited_once()
    assert save_state.await_args.kwargs.get("agent_id") == "agent-99"


@pytest.mark.asyncio
async def test_runner_invokes_gdrive_when_enabled() -> None:
    from app.services.wiki.source_sync.runner import run_wiki_source_sync
    from app.services.wiki.source_sync.schemas import WikiSourceSyncConfig

    config = WikiSourceSyncConfig(gdrive_enabled=True, gdrive_folder_id="folder-abc")
    gdrive_result = WikiSourceSyncResult(source="gdrive", published=1)

    with (
        patch("app.services.wiki.source_sync.runner.get_session") as session_ctx,
        patch(
            "app.services.wiki.source_sync.runner.sync_gdrive_folder_to_wiki",
            new=AsyncMock(return_value=gdrive_result),
        ) as sync_gdrive,
        patch(
            "app.services.wiki.source_sync.state_store.save_wiki_source_sync_state",
            new=AsyncMock(),
        ),
        patch(
            "app.services.wiki.source_sync.runner.resolve_wiki_vault_path",
            return_value="/tmp/wiki",
        ),
    ):
        db = AsyncMock()
        session_ctx.return_value.__aenter__ = AsyncMock(return_value=db)
        session_ctx.return_value.__aexit__ = AsyncMock(return_value=False)

        summary = await run_wiki_source_sync(
            llm=None, agent_id="agent-99", config=config
        )

    sync_gdrive.assert_awaited_once()
    assert sync_gdrive.await_args.kwargs["folder_id"] == "folder-abc"
    assert summary.total_published == 1
    assert summary.results[0].source == "gdrive"
