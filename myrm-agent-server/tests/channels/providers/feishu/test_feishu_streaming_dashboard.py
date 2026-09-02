"""Tests for Feishu dynamic streaming dashboard, table slicer, action fallback, and doctor."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.feishu.action_fallback import (
    FallbackActionSessionRegistry,
    build_fallback_action_card_elements,
)
from app.channels.providers.feishu.doctor import diagnose_feishu_channel
from app.channels.providers.feishu.streaming_dashboard import (
    DashboardState,
    DashboardStreamThrottler,
    ToolActionMeta,
    build_dashboard_header,
    build_dynamic_dashboard_card,
    resolve_tool_header,
)
from app.channels.providers.feishu.table_slicer import (
    is_table_row,
    is_table_separator,
    sanitize_lark_markdown,
    slice_card_markdown,
)
from app.channels.types import ActionButton

# ── Streaming Dashboard Tests ────────────────────────────────────


def test_resolve_tool_header() -> None:
    icon, title, color = resolve_tool_header("web_search", "AI news")
    assert icon == "🔍"
    assert "正在检索网络文档" in title
    assert "AI news" in title
    assert color == "watchet"

    icon2, title2, color2 = resolve_tool_header("custom_tool_name")
    assert icon2 == "⚙️"
    assert "custom_tool_name" in title2
    assert color2 == "watchet"


def test_build_dashboard_header() -> None:
    # Thinking state
    hdr_thinking = build_dashboard_header(DashboardState.THINKING)
    assert hdr_thinking["template"] == "blue"
    assert "深度思考" in hdr_thinking["title"]["content"]  # type: ignore[index]

    # Tool state
    tool_meta = ToolActionMeta(tool_name="bash", args_summary="ls -la")
    hdr_tool = build_dashboard_header(DashboardState.TOOL_RUNNING, tool_meta=tool_meta)
    assert hdr_tool["template"] == "watchet"
    assert "沙箱命令" in hdr_tool["title"]["content"]  # type: ignore[index]
    assert "耗时" in hdr_tool["subtitle"]["content"]  # type: ignore[index]

    # Completed state
    hdr_done = build_dashboard_header(DashboardState.COMPLETED)
    assert hdr_done["template"] == "green"
    assert "执行完成" in hdr_done["title"]["content"]  # type: ignore[index]


def test_build_dynamic_dashboard_card() -> None:
    meta1 = ToolActionMeta(tool_name="web_search", status="success")
    meta1.end_time = meta1.start_time + 1.2

    card = build_dynamic_dashboard_card(
        DashboardState.STREAMING,
        content="Hello Feishu!",
        card_id="card-123",
        tool_history=[meta1],
        task_id="task-abc-123456",
        cost_metadata={"cost_usd": 0.005, "model_name": "gpt-4o", "total_tokens": 1200},
    )
    assert card["config"]["wide_screen_mode"] is True
    assert card["card_id"] == "card-123"

    elements = card["elements"]
    assert isinstance(elements, list)
    # Check tool history element
    assert any("web_search" in str(el) for el in elements)
    # Check streaming content element
    assert any(
        el.get("tag") == "streaming_content" for el in elements if isinstance(el, dict)
    )
    # Check footer note with cost and task id
    note_el = next(
        (el for el in elements if isinstance(el, dict) and el.get("tag") == "note"),
        None,
    )
    assert note_el is not None
    assert "gpt-4o" in str(note_el)
    assert "task-abc" in str(note_el)


def test_dashboard_stream_throttler() -> None:
    throttler = DashboardStreamThrottler(min_interval_seconds=0.2)
    # First emit is always True
    assert throttler.should_emit("chunk 1", DashboardState.STREAMING) is True

    # Immediate second emit without state change is throttled
    assert throttler.should_emit("chunk 1 + 2", DashboardState.STREAMING) is False

    # Force emit or final chunk is always True
    assert (
        throttler.should_emit("chunk 1 + 2", DashboardState.STREAMING, is_final=True)
        is True
    )


# ── Table Slicer Tests ───────────────────────────────────────────


def test_table_row_and_separator_detection() -> None:
    assert is_table_row("| Name | Value |") is True
    assert is_table_row("  | a | b | c |  ") is True
    assert is_table_row("Normal text without pipe") is False

    assert is_table_separator("|---|---|") is True
    assert is_table_separator("| :--- | :---: | ---: |") is True
    assert is_table_separator("| Name | Value |") is False


def test_sanitize_lark_markdown() -> None:
    raw = "Normal text\n| Column 1 | Column 2 |\n|---|---|\n| data1 | data2 |"
    sanitized = sanitize_lark_markdown(raw)
    assert sanitized == raw


def test_slice_card_markdown_with_table_header_duplication() -> None:
    header = "| Col A | Col B | Col C |"
    sep = "|---|---|---|"
    rows = [f"| row {i} cell A | row {i} cell B | row {i} cell C |" for i in range(100)]
    full_text = "\n".join([header, sep] + rows)

    # Set small max_bytes to force slicing
    chunks = slice_card_markdown(full_text, max_bytes=500)
    assert len(chunks) > 1

    # Every continuation chunk containing table rows must contain the duplicated header and sep
    for idx, chunk in enumerate(chunks):
        if idx > 0 and "| row" in chunk:
            assert header in chunk, f"Chunk {idx} missing table header: {chunk[:100]}"
            assert sep in chunk, f"Chunk {idx} missing table separator: {chunk[:100]}"


# ── Action Fallback Tests ────────────────────────────────────────


def test_fallback_action_session_registry() -> None:
    registry = FallbackActionSessionRegistry(ttl_seconds=60)
    btn1 = ActionButton(action_id="act_approve", label="批准执行")
    btn2 = ActionButton(action_id="act_deny", label="拒绝授权")

    options = registry.register_actions(
        chat_id="chat_1001",
        user_id="user_2002",
        message_id="msg_3003",
        actions=[btn1, btn2],
    )
    assert len(options) == 2
    assert options[0].index == 1
    assert options[0].action_id == "act_approve"

    # Card elements generation
    card_elems = build_fallback_action_card_elements(options)
    assert len(card_elems) == 2
    assert "[1]" in str(card_elems[1])

    # Resolve with '1'
    res = registry.resolve_action("chat_1001", "user_2002", "1")
    assert res == "act_approve"

    # Session consumed, second resolve should return None
    res2 = registry.resolve_action("chat_1001", "user_2002", "1")
    assert res2 is None


def test_fallback_action_resolution_formats() -> None:
    registry = FallbackActionSessionRegistry(ttl_seconds=60)
    btn1 = ActionButton(action_id="opt_1", label="Option 1")
    btn2 = ActionButton(action_id="opt_2", label="Option 2")

    registry.register_actions("chat_1", "user_1", "msg_1", [btn1, btn2])
    assert registry.resolve_action("chat_1", "user_1", "[2]") == "opt_2"

    registry.register_actions("chat_1", "user_1", "msg_1", [btn1, btn2])
    assert registry.resolve_action("chat_1", "user_1", "【1】") == "opt_1"

    registry.register_actions("chat_1", "user_1", "msg_1", [btn1, btn2])
    assert registry.resolve_action("chat_1", "user_1", "二") == "opt_2"


# ── Doctor Diagnostics Tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_diagnose_feishu_channel() -> None:
    mock_client = MagicMock()
    mock_client.ensure_token = AsyncMock(return_value="t-fake-token")
    mock_client.bot_open_id = "ou_fake_bot_id"
    mock_client.streaming_card_create = AsyncMock(return_value=True)

    report = await diagnose_feishu_channel(
        mock_client,
        app_id="cli_12345",
        transport_mode="websocket",
    )
    assert report.is_healthy is True
    assert report.app_id == "cli_12345"
    assert len(report.checks) == 4
    assert any(c.name == "cardkit_streaming" and c.passed for c in report.checks)
