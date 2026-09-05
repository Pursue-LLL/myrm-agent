"""Unit tests for import_gemini.py — Google Gemini conversation import adapter.

Validates Gemini data export parsing, payload detection, role normalization,
parts text concatenation, timestamp resolution, and empty/unsupported handling.
"""

from __future__ import annotations

import pytest

from app.services.memory.imports.import_gemini import (
    dry_run_gemini,
    is_gemini_payload,
)


class TestGeminiPayloadDetection:
    """Detection of Google Gemini conversation exports."""

    def test_detect_via_explicit_source(self) -> None:
        payload = {"_source": "gemini", "data": {}}
        assert is_gemini_payload(payload) is True

    def test_detect_via_gemini_conversations_key(self) -> None:
        payload = {"gemini_conversations": []}
        assert is_gemini_payload(payload) is True

    def test_detect_via_structure_parts(self) -> None:
        payload = {
            "conversations": [
                {
                    "title": "Quantum Physics",
                    "messages": [
                        {
                            "role": "model",
                            "parts": [{"text": "Quantum superposition is..."}],
                        }
                    ],
                }
            ]
        }
        assert is_gemini_payload(payload) is True

    def test_reject_chatgpt_structure(self) -> None:
        payload = {
            "conversations": [
                {
                    "title": "ChatGPT Chat",
                    "mapping": {"node1": {}},
                    "current_node": "node1",
                }
            ]
        }
        assert is_gemini_payload(payload) is False

    def test_reject_unrelated_payload(self) -> None:
        payload = {"random_key": "hello"}
        assert is_gemini_payload(payload) is False


class TestGeminiDryRun:
    """Dry-run mapping of Gemini conversations to episodic memories."""

    def test_empty_conversations_warning(self) -> None:
        payload = {"_source": "gemini", "conversations": []}
        result = dry_run_gemini(payload)
        assert result.summary.source == "gemini"
        assert result.summary.status == "missing"
        assert result.summary.mapped_items == 0
        assert "gemini_no_conversations" in result.warnings

    def test_successful_conversations_parsing(self) -> None:
        payload = {
            "_source": "gemini",
            "conversations": [
                {
                    "id": "conv_gemini_01",
                    "title": "Discussion on Architecture",
                    "timestamp": 1700000000.0,
                    "model": "gemini-2.5-pro",
                    "messages": [
                        {
                            "role": "user",
                            "parts": [{"text": "How to design a distributed cache?"}],
                        },
                        {
                            "role": "model",
                            "parts": [{"text": "Use Redis cluster with consistent hashing."}],
                        },
                    ],
                },
                {
                    "id": "conv_gemini_02",
                    "title": "Python Asyncio",
                    "create_time": "2026-01-01T12:00:00Z",
                    "turns": [
                        {
                            "author": {"role": "human"},
                            "content": "Explain TaskGroup in 3.11",
                        },
                        {
                            "author": {"role": "gemini"},
                            "content": "TaskGroup provides structured concurrency.",
                        },
                    ],
                },
            ],
        }

        result = dry_run_gemini(payload)
        assert result.summary.source == "gemini"
        assert result.summary.status == "ready"
        assert result.summary.mapped_items == 2

        episodic = result.normalized_data.get("episodic")
        assert isinstance(episodic, list)
        assert len(episodic) == 2

        first = episodic[0]
        assert "Discussion on Architecture" in first["content"]
        assert "user: How to design a distributed cache?" in first["content"]
        assert "assistant: Use Redis cluster" in first["content"]
        assert first["event_type"] == "gemini_conversation"
        assert first["metadata"]["gemini_id"] == "conv_gemini_01"
        assert first["metadata"]["gemini_model"] == "gemini-2.5-pro"

        second = episodic[1]
        assert "Python Asyncio" in second["content"]
        assert "user: Explain TaskGroup" in second["content"]
        assert "assistant: TaskGroup provides structured concurrency." in second["content"]
        assert second["event_type"] == "gemini_conversation"

    def test_chats_alias_support(self) -> None:
        payload = {
            "_source": "gemini",
            "chats": [
                {
                    "title": "Quick Query",
                    "messages": [{"role": "user", "text": "What is the capital of France?"}],
                }
            ],
        }
        result = dry_run_gemini(payload)
        assert result.summary.status == "ready"
        assert result.summary.mapped_items == 1
        episodic = result.normalized_data.get("episodic")
        assert isinstance(episodic, list)
        assert "What is the capital of France?" in episodic[0]["content"]
