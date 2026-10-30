"""Which texts the cron lifecycle guard rejects: every way of stopping the service, and none of the ordinary prompts that mention it."""

from __future__ import annotations

import time

import pytest

from app.core.cron.adapters.lifecycle_guard import contains_myrm_lifecycle_command


@pytest.mark.parametrize(
    "text",
    [
        "./myrm restart",
        "./myrm  restart",
        "myrm stop",
        "cd repo && ./myrm stop",
        "./MYRM RESTART",
        "./myrm-dev restart --chrome",
        "myrm-dev stop",
        "launchctl kickstart -k gui/501/com.myrm.agent",
        "launchctl unload ~/Library/LaunchAgents/com.myrm.agent.plist",
        "launchctl bootout gui/501/com.myrm.agent",
        "launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.myrm.agent.plist",
        "launchctl load ~/Library/LaunchAgents/com.myrm.agent.plist",
        "launchctl stop com.myrm.agent",
        "launchctl  stop com.myrm.agent",
        "launchctl restart com.myrm.agent",
        "systemctl --user restart myrm-agent",
        "systemctl  --user  restart myrm-agent",
        "sudo systemctl stop myrm-agent.service",
        "systemctl start myrm-agent",
        "pkill myrm-agent-server",
        "killall myrm-agent-server",
        "killall -9 myrm-agent",
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
        "myrm restarting",
        "myrm stopwatch",
        "myrmstop",
        "launchctlstop com.myrm.agent",
        "launchctl stopped com.myrm.agent",
        "launchctl stop com.notmyrm.agent",
        "launchctl stop com.myrmx.agent",
        "systemctlrestart myrm-agent",
        "systemctl --userstop myrm-agent",
        "systemctl restarted myrm-agent",
        "systemctl restart notmyrm-agent",
        "systemctl restart myrm-agentx",
        "the watchdog killed myrm-agent",
        "pkill notmyrm-agent",
        "pkill myrm-agentx",
        "pkill the build\nthen read about myrm-agent",
    ],
)
def test_an_ordinary_text_that_only_mentions_the_service_is_accepted(text: str) -> None:
    assert contains_myrm_lifecycle_command(text) is False


def test_a_verb_and_the_service_name_are_linked_only_within_one_command_line_width() -> None:
    assert contains_myrm_lifecycle_command(f"pkill {'a' * 150} myrm-agent") is True
    assert contains_myrm_lifecycle_command(f"pkill {'a' * 250} myrm-agent") is False


@pytest.mark.parametrize("verb", ["kill", "launchctl stop", "systemctl stop"])
def test_scanning_long_text_that_repeats_a_verb_stays_linear(verb: str) -> None:
    """An unbounded verb-to-service gap re-scans the whole remaining line per verb: seconds for 100 KB."""
    text = f"{verb} " * 20000

    started = time.perf_counter()
    assert contains_myrm_lifecycle_command(text) is False

    assert time.perf_counter() - started < 1.0
