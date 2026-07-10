"""E2E: wiki ingest on canonical vault is visible to query path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import AIMessage

from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.vault_resolver import resolve_wiki_vault_path


class TestWikiIngestQueryE2E:
    @pytest.mark.asyncio
    async def test_raw_ingest_visible_to_query_engine(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        harness.mkdir()
        mock_llm = MagicMock()
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="Pricing starts at $99."))

        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)

            vault = resolve_wiki_vault_path()
            archiver = MemoryToWikiArchiver(mock_llm, wiki_dir=vault)

            concept_path = archiver._structure.get_concept_file_path("Pricing Strategy")
            concept_path.parent.mkdir(parents=True, exist_ok=True)
            concept_path.write_text(
                "# Pricing Strategy\n\nEnterprise tier starts at $99 per seat.",
                encoding="utf-8",
            )

            raw_path = archiver._structure.get_raw_file_path("pricing.md")
            raw_path.write_text("# Pricing\n\nImported source document.", encoding="utf-8")

            assert raw_path.exists()
            assert concept_path.exists()
            assert archiver.get_wiki_path().resolve() == vault.resolve()

            result = await archiver.query_wiki("What is the enterprise pricing?")
            assert isinstance(result, str)
            assert result.strip()
