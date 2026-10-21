"""Tests for consolidation → wiki raw bridge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.toolkits.memory.strategies.consolidation import ConsolidationStats


@pytest.mark.asyncio
async def test_archive_consolidation_insights_writes_raw_and_enqueues(tmp_path: Path) -> None:
    from app.services.wiki.consolidation_bridge import archive_consolidation_insights_to_wiki

    stats = ConsolidationStats(insights=("Cross-session theme: prefer Docker over K8s",))
    mock_llm = MagicMock()
    mock_structure = MagicMock()
    mock_structure.raw_dir = tmp_path / "raw"
    mock_structure.raw_dir.mkdir(parents=True)
    mock_structure.get_raw_file_path = lambda rel: mock_structure.raw_dir / rel

    mock_compiler = MagicMock()
    mock_compiler.enqueue_file = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver._structure = mock_structure
    mock_archiver._compiler = mock_compiler

    with patch(
        "app.services.wiki.vault.get_wiki_archiver",
        return_value=mock_archiver,
    ):
        await archive_consolidation_insights_to_wiki(
            stats,
            agent_id="default",
            llm=mock_llm,
        )

    written = list(mock_structure.raw_dir.rglob("consolidation_*.md"))
    assert len(written) == 1
    text = written[0].read_text(encoding="utf-8")
    assert "Consolidation insights" in text
    assert "Docker over K8s" in text
    mock_compiler.enqueue_file.assert_called_once()


@pytest.mark.asyncio
async def test_archive_consolidation_skips_when_no_insights() -> None:
    from app.services.wiki.consolidation_bridge import archive_consolidation_insights_to_wiki

    with patch("app.services.wiki.vault.get_wiki_archiver") as mock_get:
        await archive_consolidation_insights_to_wiki(
            ConsolidationStats(),
            agent_id="default",
            llm=MagicMock(),
        )
        mock_get.assert_not_called()


@pytest.mark.asyncio
async def test_archive_consolidation_skips_when_security_blocked() -> None:
    from pathlib import Path

    from myrm_agent_harness.toolkits.wiki.pipeline.raw_gate.types import RawPublishResult

    from app.services.wiki.consolidation_bridge import archive_consolidation_insights_to_wiki

    mock_structure = MagicMock()
    mock_compiler = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver._structure = mock_structure
    mock_archiver._compiler = mock_compiler

    blocked = RawPublishResult(
        relative_path="memory/consolidation_default_2026-01-01_abcd1234.md",
        absolute_path=Path("/tmp/blocked.md"),
        content_hash="hash",
        written=False,
        skipped=False,
        superseded=False,
        created=False,
        security_blocked=True,
    )

    with (
        patch(
            "app.services.wiki.vault.get_wiki_archiver",
            return_value=mock_archiver,
        ),
        patch(
            "app.services.wiki.consolidation_bridge.publish_raw",
            new_callable=AsyncMock,
            return_value=blocked,
        ),
    ):
        await archive_consolidation_insights_to_wiki(
            ConsolidationStats(insights=("Secret: sk-live-abc123456789",)),
            agent_id="default",
            llm=MagicMock(),
        )

    mock_compiler.enqueue_file.assert_not_called()
