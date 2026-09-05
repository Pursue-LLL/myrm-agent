"""Unit tests for prompt cache radar and natural language session trace search endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from app.api.statistics.prompt_cache_radar import get_prompt_cache_radar
from app.api.statistics.session_trace import search_session_traces
from app.database.models import Chat


class TestPromptCacheRadarEndpoint:
    """Test get_prompt_cache_radar endpoint calculations and aggregation."""

    @pytest.mark.asyncio
    async def test_empty_sessions_returns_zero_baseline(self) -> None:
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute.return_value = mock_result

        response = await get_prompt_cache_radar(days=7, db=mock_db)
        data = json.loads(response.body)

        assert data["code"] == 0
        payload = data["data"]
        assert payload["days"] == 7
        assert payload["sessions_tracked"] == 0
        assert payload["total_prompt_tokens"] == 0
        assert payload["fresh_input_tokens"] == 0
        assert payload["total_cache_read_tokens"] == 0
        assert payload["prompt_cache_hit_ratio"] == 0.0
        assert payload["estimated_savings_usd"] == 0.0

    @pytest.mark.asyncio
    async def test_cache_radar_with_mocked_events(self, tmp_path: Path) -> None:
        mock_db = AsyncMock()
        chat_1 = Chat(
            id="session-1",
            title="Analysis task",
            updated_at=datetime.now(timezone.utc),
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [chat_1]
        mock_db.execute.return_value = mock_result

        # Create temporary event log file
        log_dir = tmp_path / "event_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "session-1.jsonl"
        with open(log_file, "w", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "event_type": "token_usage",
                    "data": {
                        "usage": {
                            "prompt_tokens": 10000,
                            "completion_tokens": 800,
                            "cache_read_input_tokens": 7500,
                        }
                    },
                })
                + "\n"
            )

        with patch("app.api.statistics.prompt_cache_radar.settings.database.event_log_dir", str(log_dir)):
            response = await get_prompt_cache_radar(days=7, db=mock_db)
            data = json.loads(response.body)

            assert data["code"] == 0
            payload = data["data"]
            assert payload["sessions_tracked"] == 1
            assert payload["total_prompt_tokens"] == 10000
            assert payload["total_cache_read_tokens"] == 7500
            assert payload["fresh_input_tokens"] == 2500
            assert payload["total_completion_tokens"] == 800
            assert payload["prompt_cache_hit_ratio"] == 0.75
            assert payload["estimated_savings_usd"] == 0.0031


class TestSearchSessionTracesEndpoint:
    """Test natural language search of session execution traces."""

    @pytest.mark.asyncio
    async def test_search_traces_matching_prompt_or_title(self, tmp_path: Path) -> None:
        mock_db = AsyncMock()
        chat_match_title = Chat(
            id="sess-title-match",
            title="Refactor Payments Engine",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        chat_match_prompt = Chat(
            id="sess-prompt-match",
            title="General Chat",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        chat_no_match = Chat(
            id="sess-no-match",
            title="Docker compose config",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [
            chat_match_title,
            chat_match_prompt,
            chat_no_match,
        ]
        mock_db.execute.return_value = mock_result

        log_dir = tmp_path / "event_logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        # Write log for chat_match_title
        with open(log_dir / "sess-title-match.jsonl", "w", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "event_type": "task_start",
                    "data": {"input": "Optimize DB queries"},
                })
                + "\n"
            )

        # Write log for chat_match_prompt
        with open(log_dir / "sess-prompt-match.jsonl", "w", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "event_type": "task_start",
                    "data": {"input": "Inspect Payments webhook callbacks"},
                })
                + "\n"
            )

        # Write log for chat_no_match
        with open(log_dir / "sess-no-match.jsonl", "w", encoding="utf-8") as f:
            f.write(
                json.dumps({
                    "event_type": "task_start",
                    "data": {"input": "Run redis container"},
                })
                + "\n"
            )

        with patch("app.api.statistics.session_trace.settings.database.event_log_dir", str(log_dir)):
            # Search by keyword "payments"
            response = await search_session_traces(query="payments", limit=10, db=mock_db)
            data = json.loads(response.body)

            assert data["code"] == 0
            results = data["data"]
            assert len(results) == 2
            ids = [r["session_id"] for r in results]
            assert "sess-title-match" in ids
            assert "sess-prompt-match" in ids
            assert "sess-no-match" not in ids
