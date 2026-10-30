"""Which texts the cron lifecycle guard rejects: every way of stopping the service, and none of the ordinary prompts that mention it."""

from __future__ import annotations

import pytest

from app.core.cron.adapters.lifecycle_guard import contains_myrm_lifecycle_command


@pytest.mark.parametrize(
    "text",
    [
        "./myrm restart",
        "myrm stop",
        "cd repo && ./myrm stop",
        "./MYRM RESTART",
        "./myrm-dev restart --chrome",
        "myrm-dev stop",
        "launchctl kickstart -k gui/501/com.myrm.agent",
        "launchctl unload ~/Library/LaunchAgents/com.myrm.agent.plist",
        "launchctl bootout gui/501/com.myrm.agent",
        "launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.myrm.agent.plist",
        "systemctl --user restart myrm-agent",
        "sudo systemctl stop myrm-agent.service",
        "pkill myrm-agent-server",
        "pkill -f myrm-agent-frontend",
        "kill -9 $(pgrep myrm-agent-server)",
        "taskkill /F /IM myrm-agent-server.exe",
        "Stop-Process -Name myrm-agent-server",
    ],
)
def test_a_command_that_stops_or_restarts_the_service_is_rejected(text: str) -> None:
    assert contains_myrm_lifecycle_command(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Every Monday summarize the new skill releases for myrm-agent users",
        "Is a rewrite of myrm-agent overkill for a small team?",
        "myrmx restart",
        "notmyrm stop",
        "myrm-devx restart",
        "myrm status",
        "launchctl list | grep myrm",
        "systemctl status myrm-agent",
        "Summarize the news every morning",
    ],
)
def test_an_ordinary_text_that_only_mentions_the_service_is_accepted(text: str) -> None:
    assert contains_myrm_lifecycle_command(text) is False
