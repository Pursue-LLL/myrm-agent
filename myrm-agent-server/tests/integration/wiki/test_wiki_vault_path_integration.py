"""Integration: API archiver and GeneralAgent resolve the same wiki vault path."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from app.ai_agents.general_agent.agent import GeneralAgent
from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver
from app.services.wiki.vault_resolver import resolve_wiki_vault_path


class TestWikiVaultPathIntegration:
    def test_agent_and_archiver_share_canonical_path(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        harness.mkdir()
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)

            agent = GeneralAgent(
                model_cfg=MagicMock(),
                mcp_config=None,
                enable_wiki=True,
            )
            agent_path = Path(agent._resolve_wiki_base_dir() or "")
            archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=resolve_wiki_vault_path())

            assert agent_path == archiver.get_wiki_path().resolve()
            assert agent_path == (harness / "wiki").resolve()

    def test_ingest_visible_on_same_vault(self, tmp_path: Path) -> None:
        harness = tmp_path / "harness"
        harness.mkdir()
        with patch("app.config.settings.settings") as mock_settings:
            mock_settings.database.harness_dir = str(harness)
            mock_settings.database.state_dir = str(tmp_path)

            vault = resolve_wiki_vault_path()
            archiver = MemoryToWikiArchiver(MagicMock(), wiki_dir=vault)
            raw_path = archiver._structure.get_raw_file_path("integration_probe.md")
            raw_path.parent.mkdir(parents=True, exist_ok=True)
            raw_path.write_text("# Integration\n\nWiki vault path integration probe.", encoding="utf-8")

            agent = GeneralAgent(model_cfg=MagicMock(), mcp_config=None, enable_wiki=True)
            assert Path(agent._resolve_wiki_base_dir() or "").resolve() == vault.resolve()
            assert raw_path.exists()
