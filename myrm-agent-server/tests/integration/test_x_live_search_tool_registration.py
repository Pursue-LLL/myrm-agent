"""Integration & unit tests for x-live-search PTC skill architecture.

Verifies:
1. x-live-search skill uses PTC paradigm (0 vendor Action Tools registered at Turn1).
2. Standard sandbox execution script (search.py) validation, error handling, parameter parsing.
"""

from __future__ import annotations

import importlib.util
import io
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.skills.gates.oauth_availability import X_LIVE_SEARCH_SKILL_ID

SCRIPT_PATH = Path(__file__).resolve().parents[2] / "assets" / "prebuilt_skills" / "x-live-search" / "scripts" / "search.py"


def _load_search_script():
    spec = importlib.util.spec_from_file_location("x_search_script", SCRIPT_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


x_search_script = _load_search_script()


def _make_search_mixin(*, skill_ids: list[str] | None) -> object:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.enable_web_search = True
    mixin.search_service_cfg = MagicMock()
    mixin.reranker_config = None
    mixin.enable_advanced_retrieval = False
    mixin.embedding_config = None
    mixin.fetch_raw_webpage = False
    mixin.image_generation_params = None
    mixin.video_generation_params = None
    mixin.tts_params = None
    mixin.search_depth = "normal"
    mixin.model_cfg = MagicMock(model="test-model", api_key="k", base_url="http://localhost")
    mixin.skill_ids = skill_ids or []
    return mixin


def test_x_live_search_registers_zero_action_tools() -> None:
    """x-live-search must not register any vendor Action Tools into Turn1 tools (PTC decoupled)."""
    mixin = _make_search_mixin(skill_ids=[X_LIVE_SEARCH_SKILL_ID])
    tools: list[object] = []

    with patch("app.config.deploy_mode.is_local_mode", return_value=True):
        mixin._setup_search_and_basic_tools(tools)

    assert not any(getattr(t, "name", None) == "x_search_tool" for t in tools)


class TestXLiveSearchSandboxScript:
    def test_normalize_handles(self) -> None:
        assert x_search_script._normalize_handles(["@elonmusk", "sama", "  @openai "]) == [
            "elonmusk",
            "sama",
            "openai",
        ]

    def test_normalize_handles_exceed_max(self) -> None:
        with pytest.raises(ValueError, match="Maximum 20 handles"):
            x_search_script._normalize_handles([f"user{i}" for i in range(22)])

    def test_normalize_handles_at_max_boundary(self) -> None:
        handles = x_search_script._normalize_handles([f"user{i}" for i in range(20)])
        assert len(handles) == 20

    def test_validate_date_range(self) -> None:
        assert x_search_script._validate_date_range("2026-08-01", "2026-08-31") is None
        assert "must be YYYY-MM-DD" in (x_search_script._validate_date_range("2026/08/01", "") or "")
        assert "must be on or before" in (x_search_script._validate_date_range("2026-08-31", "2026-08-01") or "")
        assert "is in the future" in (x_search_script._validate_date_range("2099-01-01", "2099-01-02") or "")

    def test_missing_credentials_fails_cleanly(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Guard against a dev/CI machine exporting XAI_API_KEY, which would
        # silently bypass the missing-credentials branch.
        monkeypatch.delenv("XAI_API_KEY", raising=False)
        monkeypatch.delenv("XAI_BASE_URL", raising=False)
        buf = io.StringIO()
        with redirect_stderr(buf):
            ret = x_search_script.execute_search("test query", api_key="")
        assert ret == 1
        assert "xAI credentials not configured" in buf.getvalue()

    def test_mutually_exclusive_handles_fail(self) -> None:
        buf = io.StringIO()
        with redirect_stderr(buf):
            ret = x_search_script.execute_search(
                "test query",
                allowed_handles=["a"],
                excluded_handles=["b"],
                api_key="test-key",
            )
        assert ret == 1
        assert "cannot be used together" in buf.getvalue()

    def test_extract_response_text_both_formats(self) -> None:
        # 1. direct output_text
        payload1 = {"output_text": "Direct answer here"}
        assert x_search_script._extract_response_text(payload1) == "Direct answer here"

        # 2. structured output list
        payload2 = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {"type": "output_text", "text": "Structured part 1"},
                        {"type": "text", "text": "Structured part 2"},
                    ],
                }
            ]
        }
        assert x_search_script._extract_response_text(payload2) == "Structured part 1\n\nStructured part 2"

    def test_extract_inline_citations(self) -> None:
        payload = {
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": "Check this out",
                            "annotations": [
                                {"type": "url_citation", "url": "https://x.com/user/status/123", "title": "Post Title"}
                            ],
                        }
                    ],
                }
            ]
        }
        citations = x_search_script._extract_inline_citations(payload)
        assert len(citations) == 1
        assert citations[0]["url"] == "https://x.com/user/status/123"
        assert citations[0]["title"] == "Post Title"

    def test_validate_base_url_security(self) -> None:
        # Allowed host
        assert x_search_script._validate_base_url("https://api.x.ai/v1") == "https://api.x.ai/v1"
        # Disallowed scheme / host fallback to default
        assert x_search_script._validate_base_url("http://malicious.site/v1") == x_search_script._DEFAULT_XAI_BASE_URL
        assert x_search_script._validate_base_url("https://attacker.com/v1") == x_search_script._DEFAULT_XAI_BASE_URL

    def test_source_label(self) -> None:
        # xAI `url_citation` titles are inline citation numbers ("1", "2"), not page titles.
        assert x_search_script._source_label("1", "https://x.com/elonmusk/status/123") == "@elonmusk post"
        assert x_search_script._source_label("", "https://x.com/karpathy") == "@karpathy"
        assert x_search_script._source_label("4", "https://www.x.com/sama/status/9") == "@sama post"
        # Real page titles are preserved.
        assert x_search_script._source_label("My Blog Post", "https://example.com/post") == "My Blog Post"
        # Numeric title on a non-x.com URL falls back to the URL itself.
        assert x_search_script._source_label("2", "https://example.com/post") == "https://example.com/post"
        # Reserved x.com path prefixes carry no handle; fall back to the URL.
        assert x_search_script._source_label("3", "https://x.com/i/lists/1") == "https://x.com/i/lists/1"
        assert x_search_script._source_label("5", "https://x.com/search?q=ai") == "https://x.com/search?q=ai"
