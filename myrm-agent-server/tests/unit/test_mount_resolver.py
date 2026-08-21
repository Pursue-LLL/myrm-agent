"""Tests for app.ai_agents.general_agent.mount_resolver — Channel x Profile tool mount resolution."""

from unittest.mock import MagicMock, patch
import pytest

from app.ai_agents.general_agent.mount_resolver import (
    ResolvedMountPlan,
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
    assert plan.mount_desktop_prompt is True
    assert plan.mount_cli_context is True


def test_resolve_agent_mount_im_channel_drops_browser_and_desktop() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    for im_channel in ["feishu", "wecom", "dingtalk", "telegram", "slack", "discord"]:
        with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=True):
            plan = resolve_agent_mount(im_channel, agent)

        assert plan.mount_browser is False, f"Browser tools should not mount on {im_channel}"
        assert plan.mount_computer_use is False, f"Desktop tools should not mount on {im_channel}"
        assert plan.mount_desktop_prompt is False, f"Desktop rules should not inject on {im_channel}"
        assert plan.mount_cli_context is False, f"CLI context should not inject on {im_channel}"


def test_resolve_agent_mount_cron_channel() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=True):
        plan = resolve_agent_mount("cron", agent)

    assert plan.mount_browser is False
    assert plan.mount_computer_use is False
    assert plan.mount_desktop_prompt is False
    assert plan.mount_cli_context is True


def test_resolve_agent_mount_computer_use_host_unsupported() -> None:
    agent = MagicMock()
    agent.enable_browser = True
    agent.enable_computer_use = True

    with patch("app.config.computer_use_deploy.is_computer_use_deploy_supported", return_value=False):
        plan = resolve_agent_mount("web_chat", agent)

    assert plan.mount_browser is True
    assert plan.mount_computer_use is False
    assert plan.mount_desktop_prompt is False
