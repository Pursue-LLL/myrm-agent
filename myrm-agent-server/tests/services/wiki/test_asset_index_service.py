"""Tests for wiki asset index scheduling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.wiki import asset_index_service


@pytest.mark.asyncio
async def test_schedule_wiki_asset_index_dedupes_per_vault() -> None:
    archiver = MagicMock()
    archiver._structure.base_dir = "/tmp/vault-a"
    gate = asyncio.Event()
    run_count = 0

    async def slow_index(
        _archiver: MagicMock,
        _vault_key: str,
        *,
        agent_id: str | None,
    ) -> None:
        nonlocal run_count
        run_count += 1
        if run_count == 1:
            asset_index_service._pending_asset_index_reschedule.add(_vault_key)
        await gate.wait()

    with patch.object(asset_index_service, "_active_asset_index_tasks", {}):
        with patch.object(asset_index_service, "_pending_asset_index_reschedule", set()):
            with patch.object(asset_index_service, "_run_asset_index_background", side_effect=slow_index):
                asset_index_service.schedule_wiki_asset_index(archiver, agent_id="agent-a")
                asset_index_service.schedule_wiki_asset_index(archiver, agent_id="agent-a")

                assert len(asset_index_service._active_asset_index_tasks) == 1
                assert "/tmp/vault-a" in asset_index_service._pending_asset_index_reschedule
                pending = next(iter(asset_index_service._active_asset_index_tasks.values()))
                pending.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await pending


@pytest.mark.asyncio
async def test_schedule_wiki_asset_index_returns_before_index_finishes() -> None:
    """Import path must not block HTTP while vision indexing runs."""
    archiver = MagicMock()
    archiver._structure.base_dir = "/tmp/vault-b"
    gate = asyncio.Event()

    async def slow_run(_archiver: MagicMock) -> MagicMock:
        await gate.wait()
        return MagicMock(indexed=1, skipped=0, failed=0)

    with patch.object(asset_index_service, "_active_asset_index_tasks", {}):
        with patch.object(asset_index_service, "_pending_asset_index_reschedule", set()):
            with patch.object(asset_index_service, "run_wiki_asset_index", side_effect=slow_run):
                with patch(
                    "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot",
                    new=AsyncMock(),
                ):
                    with patch(
                        "app.services.wiki.structural_stats_cache.invalidate_structural_lint_cache",
                    ):
                        asset_index_service.schedule_wiki_asset_index(archiver, agent_id="agent-b")
                        task = asset_index_service._active_asset_index_tasks["/tmp/vault-b"]
                        assert not task.done()
                        gate.set()
                        await task


@pytest.mark.asyncio
async def test_run_asset_index_background_reruns_when_reschedule_flagged() -> None:
    archiver = MagicMock()
    structure = MagicMock()
    archiver._structure = structure
    run_count = 0

    async def mock_run(_archiver: MagicMock) -> MagicMock:
        nonlocal run_count
        run_count += 1
        if run_count == 1:
            asset_index_service._pending_asset_index_reschedule.add("/tmp/vault-a")
        return MagicMock(indexed=1, skipped=0, failed=0)

    with patch.object(asset_index_service, "_pending_asset_index_reschedule", set()):
        with patch.object(asset_index_service, "run_wiki_asset_index", side_effect=mock_run):
            with patch(
                "app.services.wiki.structural_stats_cache.invalidate_structural_lint_cache",
            ):
                with patch(
                    "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot",
                    new=AsyncMock(),
                ) as mock_publish:
                    await asset_index_service._run_asset_index_background(
                        archiver,
                        "/tmp/vault-a",
                        agent_id="agent-a",
                    )
                    assert run_count == 2
                    assert mock_publish.await_count == 2


@pytest.mark.asyncio
async def test_run_asset_index_background_publishes_ingest_snapshot() -> None:
    archiver = MagicMock()
    structure = MagicMock()
    archiver._structure = structure

    with patch.object(
        asset_index_service,
        "run_wiki_asset_index",
        new=AsyncMock(return_value=MagicMock(indexed=1, skipped=0, failed=0)),
    ):
        with patch(
            "app.services.wiki.structural_stats_cache.invalidate_structural_lint_cache",
        ):
            with patch(
                "app.services.wiki.ingest_events.publish_wiki_ingest_snapshot",
                new=AsyncMock(),
            ) as mock_publish:
                await asset_index_service._run_asset_index_background(
                    archiver,
                    "/tmp/vault-a",
                    agent_id="agent-scope",
                )
                mock_publish.assert_awaited_once_with(
                    archiver,
                    agent_id="agent-scope",
                    stats_refresh_required=True,
                )
