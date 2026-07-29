"""Deep research wiki vault callback — publish_raw integration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_vault_research_to_wiki_uses_publish_raw(tmp_path: Path) -> None:
    from app.services.agent.stream_session.stream_lane_factory import _build_wiki_vault_callback

    class _Result:
        agent_results = [
            {
                "task": "compare tools",
                "result": "x" * 250,
                "partial": False,
            }
        ]

    params = MagicMock()
    params.agent_id = "default"
    params.chat_id = "chat-1"
    params.model_cfg = MagicMock()
    params.model_cfg.api_keys = None

    wiki_base = tmp_path / "wiki"
    wiki_base.mkdir()
    mock_llm = MagicMock()
    mock_archiver = MagicMock()
    mock_archiver._compiler.enqueue_file = MagicMock()

    callback = _build_wiki_vault_callback(params)

    with (
        patch(
            "app.services.wiki.vault_resolver.resolve_wiki_vault_path",
            return_value=wiki_base,
        ),
        patch(
            "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
            new_callable=AsyncMock,
            return_value=mock_llm,
        ),
        patch(
            "app.services.wiki.vault_service.get_wiki_archiver",
            return_value=mock_archiver,
        ),
    ):
        await callback(_Result())

    raw_files = list((wiki_base / "raw").rglob("deep_research_*.md"))
    assert len(raw_files) == 1
    assert "compare tools" in raw_files[0].read_text(encoding="utf-8")
    mock_archiver._compiler.enqueue_file.assert_called_once()


@pytest.mark.asyncio
async def test_vault_research_blocks_credential_content(tmp_path: Path) -> None:
    from app.services.agent.stream_session.stream_lane_factory import _build_wiki_vault_callback

    secret = "sk-1234567890abcdefghijklmnopqrstuvwxyz1234567890abcd"

    class _Result:
        agent_results = [
            {
                "task": "leak",
                "result": f"Findings with key OPENAI_API_KEY={secret}\n" + ("detail " * 40),
                "partial": False,
            }
        ]

    params = MagicMock()
    params.agent_id = "default"
    params.chat_id = "chat-1"
    params.model_cfg = MagicMock()
    params.model_cfg.api_keys = None

    wiki_base = tmp_path / "wiki"
    wiki_base.mkdir()

    callback = _build_wiki_vault_callback(params)

    with patch(
        "app.services.wiki.vault_resolver.resolve_wiki_vault_path",
        return_value=wiki_base,
    ):
        await callback(_Result())

    raw_files = list((wiki_base / "raw").rglob("deep_research_*.md"))
    assert raw_files == []
