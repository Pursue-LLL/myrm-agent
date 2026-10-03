"""Real-component E2E: wiki archive gate thresholds (turns 10->5, content 500->300).

Runs the real MemoryToWikiArchiver pipeline (real LLM from .env.test, real
publish_raw ingestion, tmp-isolated vault) and asserts the relaxed gate
behavior at the old/new boundary: turns=6 passes the new gate (5) but would
have been skipped by the old gate (10); content in [300, 500) passes the new
content gate but would have been skipped by the old one.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from myrm_agent_harness.toolkits.wiki import WikiConfig

from app.services.wiki.memory_to_wiki import MemoryToWikiArchiver

pytestmark = pytest.mark.e2e


def _real_llm() -> BaseChatModel:
    """Build the real test model from .env.test (loaded by pytest env config)."""
    from langchain_openai import ChatOpenAI

    model = os.environ["BASIC_MODEL"]
    _, _, short_name = model.partition("/")
    return ChatOpenAI(
        model=short_name or model,
        base_url=os.environ["BASIC_BASE_URL"],
        api_key=os.environ["BASIC_API_KEY"],
        timeout=60,
    )


def _harness_notes(last_idx: int, body_len: int) -> str:
    """Harness SessionNotes with a controlled body length (uses the _meta branch)."""
    return json.dumps(
        {
            "_meta": {"last_updated_message_idx": last_idx},
            "task_spec": "Validate wiki archive gate thresholds with the real pipeline.",
            "key_findings": "K" * body_len,
            "worklog": "Ran the real archive pipeline end to end.",
        }
    )


@pytest.fixture
def real_archiver(tmp_path: Path) -> MemoryToWikiArchiver:
    return MemoryToWikiArchiver(
        llm=_real_llm(),
        wiki_dir=str(tmp_path / "vault"),
        config=WikiConfig(),
    )


class TestArchiveGateValues:
    def test_gate_thresholds_match_relaxed_contract(self) -> None:
        """The gate contract under test: min turns 5, min content 300."""
        config = WikiConfig()
        assert config.auto_archive_min_turns == 5
        import inspect

        src = inspect.getsource(MemoryToWikiArchiver.archive_memory)
        assert "len(content) < 300" in src


class TestEstimateTurnCount:
    def test_real_notes_turn_proxy(self) -> None:
        """estimate_turn_count_from_notes maps last_updated_message_idx to turns."""
        assert MemoryToWikiArchiver.estimate_turn_count_from_notes(_harness_notes(6, 10)) == 6


class TestRealArchivePipeline:
    async def test_archive_at_relaxed_turn_and_content_gate(self, real_archiver: MemoryToWikiArchiver, tmp_path: Path) -> None:
        """turns=6 + content in [300, 500) archives via the real pipeline.

        Both values sit in the band that the old gates (10 turns / 500 chars)
        would have rejected, so a True result proves the relaxed gates are live.
        """
        notes = _harness_notes(6, 320)
        content = real_archiver._format_memory_as_document(json.loads(notes))
        assert 300 <= len(content) < 500, f"fixture drifted out of gate band: {len(content)}"

        turns = MemoryToWikiArchiver.estimate_turn_count_from_notes(notes)
        assert 5 <= turns < 10

        archived = await real_archiver.archive_memory(notes, conversation_turns=turns)
        assert archived is True

        raw_files = list((tmp_path / "vault").rglob("conversation_*.md"))
        assert raw_files, "archive reported success but no raw conversation file landed in vault"

    async def test_skip_below_content_gate(self, real_archiver: MemoryToWikiArchiver) -> None:
        """Content shorter than 300 chars is still skipped after relaxation."""
        notes = _harness_notes(6, 40)
        content = real_archiver._format_memory_as_document(json.loads(notes))
        assert len(content) < 300

        archived = await real_archiver.archive_memory(notes, conversation_turns=6)
        assert archived is False
