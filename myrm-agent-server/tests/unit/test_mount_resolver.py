"""Tests for app.ai_agents.general_agent.mount_resolver — Channel x Profile tool mount resolution."""

from unittest.mock import MagicMock, patch

import pytest

from app.ai_agents.general_agent.mount_resolver import (
    resolve_agent_mount,
)


def test_resolve_agent_mount_web_chat_all_enabled() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=True):
        plan = resolve_agent_mount("web_chat", agent)

    assert plan.mount_browser is True
    assert plan.mount_computer_use is True


def test_resolve_agent_mount_im_channel_drops_browser_and_desktop() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    for im_channel in ["feishu", "wecom", "dingtalk", "telegram", "slack", "discord"]:
        with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=True):
            plan = resolve_agent_mount(im_channel, agent)

        assert plan.mount_browser is False, f"Browser tools should not mount on {im_channel}"
        assert plan.mount_computer_use is False, f"Desktop tools should not mount on {im_channel}"


def test_resolve_agent_mount_cron_channel() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=True):
        plan = resolve_agent_mount("cron", agent)

    assert plan.mount_browser is False
    assert plan.mount_computer_use is False


def test_resolve_agent_mount_computer_use_host_unsupported() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=False):
        plan = resolve_agent_mount("web_chat", agent)

    assert plan.mount_browser is True
    assert plan.mount_computer_use is False


@pytest.mark.parametrize(
    ("channel", "prompt_mode", "expected"),
    [
        ("web_chat", "full", True),
        ("web_chat", "lean", True),
        ("web_chat", "search", False),
        ("web_chat", "naked", False),
        *[
            (channel, "full", False)
            for channel in (
                "feishu",
                "wecom",
                "dingtalk",
                "telegram",
                "slack",
                "discord",
                "cron",
                "kanban",
                "eval",
                "voice_bridge",
                "realtime_voice",
            )
        ],
    ],
)
def test_widget_declaration_is_mounted_only_for_web_chat_conversations(channel: str, prompt_mode: str, expected: bool) -> None:
    agent = MagicMock()
    agent.prompt_mode = prompt_mode

    assert resolve_agent_mount(channel, agent).mount_widget_capability is expected
