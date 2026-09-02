"""Integration & unit tests for x-live-search PTC skill architecture.

Verifies:
1. x-live-search skill uses PTC paradigm (0 vendor Action Tools registered at Turn1).
2. Standard sandbox execution script (search.py) validation, error handling, parameter parsing.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout
from unittest.mock import MagicMock, patch

from app.core.skills.gates.oauth_availability import X_LIVE_SEARCH_SKILL_ID
from assets.prebuilt_skills.x_live_search.scripts import search as x_search_script  # type: ignore[import-not-found]


def _make_search_mixin(*, skill_ids: list[str] | None) -> object:
    from app.ai_agents.general_agent.tool_setup import ToolSetupMixin

    mixin = ToolSetupMixin.__new__(ToolSetupMixin)
    mixin.enable_web_search = True
    mixin.search_service_cfg = MagicMock()
    mixin.reranker_config = None
    mixin.enable_advanced_retrieval = False
    mixin.embedding_config = None
    mixin.fetch_raw_webpage = False
    mixin.enable_render_ui = False
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
        import pytest

        with pytest.raises(ValueError, match="Maximum 10 handles"):
            x_search_script._normalize_handles([f"user{i}" for i in range(12)])

    def test_validate_date_range(self) -> None:
        assert x_search_script._validate_date_range("2026-08-01", "2026-08-31") is None
        assert "must be YYYY-MM-DD" in (x_search_script._validate_date_range("2026/08/01", "") or "")
        assert "must be on or before" in (x_search_script._validate_date_range("2026-08-31", "2026-08-01") or "")
        assert "is in the future" in (x_search_script._validate_date_range("2099-01-01", "2099-01-02") or "")

    def test_missing_credentials_fails_cleanly(self) -> None:
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
