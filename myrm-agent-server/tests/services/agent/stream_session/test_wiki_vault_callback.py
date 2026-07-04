"""Tests for _build_wiki_vault_callback in stream_lane_factory."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@dataclass
class _FakeModelCfg:
    api_keys: dict[str, str] | None = None


@dataclass
class _FakeParams:
    enable_wiki: bool = True
    chat_id: str = "test-session-123"
    model_cfg: _FakeModelCfg = field(default_factory=_FakeModelCfg)


@dataclass
class _FakeResult:
    report: str = "Full research report"
    agent_results: list[dict[str, Any]] = field(default_factory=list)
    error: str | None = None


class TestBuildWikiVaultCallback:
    """Unit tests for _build_wiki_vault_callback logic."""

    def _get_callback_factory(self):
        from app.services.agent.stream_session.stream_lane_factory import _build_wiki_vault_callback
        return _build_wiki_vault_callback

    def test_returns_callable(self):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)
        assert callable(callback)

    @pytest.mark.asyncio
    async def test_skips_when_wiki_dir_not_exists(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        result = _FakeResult(agent_results=[{"task": "Test", "result": "x" * 300}])

        with patch("pathlib.Path.expanduser", return_value=tmp_path / "nonexistent"):
            await callback(result)

    @pytest.mark.asyncio
    async def test_skips_when_no_agent_results(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "wiki"
        wiki_dir.mkdir(parents=True)

        result = _FakeResult(agent_results=[])

        with patch("pathlib.Path.expanduser", return_value=tmp_path):
            with patch.object(Path, "exists", return_value=True):
                await callback(result)

    @pytest.mark.asyncio
    async def test_skips_partial_results(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        result = _FakeResult(
            agent_results=[
                {"task": "Partial task", "result": "x" * 300, "partial": True},
            ]
        )

        wiki_dir = tmp_path / "sandbox" / "wiki"
        wiki_dir.mkdir(parents=True)

        with patch("pathlib.Path.expanduser", return_value=tmp_path / "sandbox" / "wiki"):
            with patch.object(Path, "exists", return_value=True):
                await callback(result)

    @pytest.mark.asyncio
    async def test_skips_short_content(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        wiki_dir.mkdir(parents=True)
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        result = _FakeResult(
            agent_results=[{"task": "Short", "result": "Too short"}]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
        ):
            await callback(result)

        written = list(raw_dir.glob("*.md"))
        assert len(written) == 0

    @pytest.mark.asyncio
    async def test_writes_files_with_frontmatter(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams(chat_id="sess-abc")
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        result = _FakeResult(
            agent_results=[
                {"task": "AI Models Overview", "result": "A" * 300},
                {"task": "Performance Analysis", "result": "B" * 400},
            ]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()

        mock_llm = MagicMock()

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.config.WikiConfig",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.pipeline.compiler.WikiCompiler",
                return_value=mock_compiler,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
                new_callable=AsyncMock,
                return_value=mock_llm,
            ),
        ):
            await callback(result)

        written = list(raw_dir.glob("*.md"))
        assert len(written) == 2

        for fp in written:
            content = fp.read_text(encoding="utf-8")
            assert content.startswith("---\n")
            assert "source: deep_research" in content
            assert "session_id: \"sess-abc\"" in content

        assert mock_compiler.enqueue_file.call_count == 2

    @pytest.mark.asyncio
    async def test_escapes_quotes_in_yaml(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        result = _FakeResult(
            agent_results=[
                {"task": 'Task with "quotes" inside', "result": "C" * 300},
            ]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.config.WikiConfig",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.pipeline.compiler.WikiCompiler",
                return_value=mock_compiler,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
        ):
            await callback(result)

        written = list(raw_dir.glob("*.md"))
        assert len(written) == 1
        content = written[0].read_text(encoding="utf-8")
        assert '\\"quotes\\"' in content

    @pytest.mark.asyncio
    async def test_sanitizes_filename(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        result = _FakeResult(
            agent_results=[
                {"task": "Task with spaces/and special!chars", "result": "D" * 300},
            ]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.config.WikiConfig",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.pipeline.compiler.WikiCompiler",
                return_value=mock_compiler,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
        ):
            await callback(result)

        written = list(raw_dir.glob("*.md"))
        assert len(written) == 1
        filename = written[0].name
        assert " " not in filename
        assert "/" not in filename
        assert "!" not in filename

    @pytest.mark.asyncio
    async def test_mixed_results_filters_correctly(self, tmp_path: Path):
        """Mix of complete, partial, and short — only valid complete entries pass."""
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        result = _FakeResult(
            agent_results=[
                {"task": "Good result", "result": "G" * 300},
                {"task": "Partial", "result": "P" * 300, "partial": True},
                {"task": "Too short", "result": "short"},
                {"task": "Another good", "result": "H" * 500},
                {"task": "Empty", "result": ""},
            ]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.config.WikiConfig",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.pipeline.compiler.WikiCompiler",
                return_value=mock_compiler,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
        ):
            await callback(result)

        written = list(raw_dir.glob("*.md"))
        assert len(written) == 2
        assert mock_compiler.enqueue_file.call_count == 2

    @pytest.mark.asyncio
    async def test_result_without_agent_results_attribute(self, tmp_path: Path):
        """Result object without agent_results attr → graceful skip via getattr."""
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        wiki_dir.mkdir(parents=True)

        class _BareResult:
            report = "some report"

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
        ):
            await callback(_BareResult())

    @pytest.mark.asyncio
    async def test_long_task_name_truncated_in_filename(self, tmp_path: Path):
        """Task names > 60 chars are truncated for filename safety."""
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        long_task = "A" * 100
        result = _FakeResult(
            agent_results=[{"task": long_task, "result": "F" * 300}]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        mock_compiler = MagicMock()
        mock_compiler.enqueue_file = MagicMock()

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.config.WikiConfig",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.pipeline.compiler.WikiCompiler",
                return_value=mock_compiler,
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
                new_callable=AsyncMock,
                return_value=MagicMock(),
            ),
        ):
            await callback(result)

        written = list(raw_dir.glob("*.md"))
        assert len(written) == 1
        filename = written[0].name
        # Format: deep_research_{YYYYMMDD_HHMMSS}_{idx}_{safe_task}.md
        # "deep_research_" = 14 chars, timestamp = 15 chars, idx = ~2 chars
        # With 100-char task truncated to 60: total should be well under 150
        assert len(filename) < 120
        # Verify the task portion is 60 chars (not 100)
        assert "A" * 61 not in filename

    @pytest.mark.asyncio
    async def test_compiler_failure_does_not_raise(self, tmp_path: Path):
        factory = self._get_callback_factory()
        params = _FakeParams()
        callback = factory(params)

        wiki_dir = tmp_path / "sandbox" / "wiki"
        raw_dir = wiki_dir / "raw"
        raw_dir.mkdir(parents=True)

        result = _FakeResult(
            agent_results=[{"task": "Valid task", "result": "E" * 300}]
        )

        mock_structure = MagicMock()
        mock_structure.raw_dir = raw_dir

        with (
            patch("pathlib.Path.expanduser", return_value=wiki_dir),
            patch.object(Path, "exists", return_value=True),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.structure.WikiStructure",
                return_value=mock_structure,
            ),
            patch(
                "myrm_agent_harness.toolkits.wiki.core.config.WikiConfig",
                return_value=MagicMock(),
            ),
            patch(
                "myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config",
                new_callable=AsyncMock,
                side_effect=RuntimeError("LLM unavailable"),
            ),
        ):
            await callback(result)
