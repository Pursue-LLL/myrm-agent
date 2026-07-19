"""Unit tests for render_ui surface mount gate helpers."""

from __future__ import annotations

from app.ai_agents.general_agent.tool_setup import _should_mount_render_ui_tools


def test_mount_gate_requires_enable_flag() -> None:
    assert not _should_mount_render_ui_tools(
        enable_render_ui=False,
        channel_name="web_chat",
        client_surface="web",
    )


def test_mount_gate_allows_web_chat_web_and_tauri() -> None:
    assert _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface="web",
    )
    assert _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface="tauri",
    )
    assert _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface=None,
    )


def test_mount_gate_blocks_im_cron_and_headless() -> None:
    assert not _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="telegram_bot",
        client_surface="web",
    )
    assert not _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="cron",
        client_surface=None,
    )
    assert not _should_mount_render_ui_tools(
        enable_render_ui=True,
        channel_name="web_chat",
        client_surface="headless",
    )
