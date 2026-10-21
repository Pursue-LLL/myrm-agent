"""Tests for router stream scrubber and WeCom progress bubble stage normalization."""

from __future__ import annotations

from app.channels.routing.router_stream_scrubber import (
    normalize_progress_stage,
    scrub_thinking_content,
)


def test_scrub_thinking_content() -> None:
    # Closed think tag
    text = "<think>Analyzing user request...</think>Here is the final result."
    cleaned, is_thinking = scrub_thinking_content(text)
    assert cleaned == "Here is the final result."
    assert is_thinking is False

    # Open think tag
    open_text = "<think>Still thinking about the plan..."
    cleaned_open, is_thinking_open = scrub_thinking_content(open_text)
    assert cleaned_open == ""
    assert is_thinking_open is True

    # Normal text without thinking
    normal = "Hello world!"
    cleaned_normal, is_thinking_normal = scrub_thinking_content(normal)
    assert cleaned_normal == "Hello world!"
    assert is_thinking_normal is False

    # Upper case tags
    upper = "<THINK>Thinking deeply...</THINK>Completed."
    cleaned_upper, is_thinking_upper = scrub_thinking_content(upper)
    assert cleaned_upper == "Completed."
    assert is_thinking_upper is False


def test_normalize_progress_stage() -> None:
    # Empty
    assert normalize_progress_stage("") == "⏳ 思考中..."

    # Search
    assert normalize_progress_stage("searching for AI news") == "🔍 searching for AI news"
    assert normalize_progress_stage("🔍 检索数据") == "🔍 检索数据"

    # Web fetch
    assert normalize_progress_stage("fetch url content") == "🌐 fetch url content"

    # Terminal / Bash
    assert normalize_progress_stage("exec bash command") == "⚡ exec bash command"

    # File / Doc
    assert normalize_progress_stage("read file data.json") == "📂 read file data.json"

    # Tool JSON stripping
    assert normalize_progress_stage("search_tool({'query': 'AI'})") == "🔍 search_tool()"
