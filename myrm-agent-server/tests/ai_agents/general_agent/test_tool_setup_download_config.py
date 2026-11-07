"""A chat's browser keeps downloads under its workspace, and a page saves one on its own only where the agent may download unasked.

Nobody can be asked about a download a page starts, so the permission policy decides beforehand and only ALLOW admits
it. The decision is the one the agent's own ``download_url`` call would get (``browser_download``): the channel preset,
the local-mode relaxation and the rules of the chat all count.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest
from myrm_agent_harness.agent.security.channel_presets import build_channel_security_config
from myrm_agent_harness.agent.security.types import PermissionAction, PermissionRule, SecurityConfig
from myrm_agent_harness.core.artifacts.paths import resolve_workspace_downloads_dir

from app.ai_agents.general_agent.tool_setup.common import _build_download_config

_ADDRESS = "https://files.example/report.pdf"


def _admits(config: SecurityConfig, workspace: Path) -> bool:
    admit = _build_download_config(str(workspace), config).admit_page_started
    assert admit is not None
    return admit(_ADDRESS)


def _with_rule(config: SecurityConfig, action: PermissionAction) -> SecurityConfig:
    return replace(config, ruleset=(*config.ruleset, PermissionRule("browser_download", "*", action)))


class TestDownloadsFolder:
    def test_files_go_under_the_workspace_of_the_chat_and_nothing_is_created_yet(self, tmp_path: Path) -> None:
        config = _build_download_config(str(tmp_path), build_channel_security_config("web_chat"))

        assert config.downloads_dir == resolve_workspace_downloads_dir(tmp_path)
        assert not config.downloads_dir.exists()


class TestPageStartedPolicy:
    @pytest.mark.parametrize(
        ("channel", "local", "admitted"),
        [
            ("web_chat", True, True),  # the user owns the machine: the agent may download unasked
            ("web_chat", False, False),  # elsewhere the agent is asked first
            ("telegram", True, False),  # a messaging channel has no browser downloads at all
            ("telegram", False, False),
        ],
    )
    def test_the_channel_and_the_deployment_decide(self, tmp_path: Path, channel: str, local: bool, admitted: bool) -> None:
        config = build_channel_security_config(channel, local_mode=local)

        assert _admits(config, tmp_path) is admitted

    def test_a_rule_that_denies_downloads_refuses_even_where_the_user_owns_the_machine(self, tmp_path: Path) -> None:
        config = _with_rule(build_channel_security_config("web_chat", local_mode=True), PermissionAction.DENY)

        assert _admits(config, tmp_path) is False

    def test_a_rule_that_allows_downloads_admits_even_where_the_agent_is_asked_by_default(self, tmp_path: Path) -> None:
        config = _with_rule(build_channel_security_config("web_chat", local_mode=False), PermissionAction.ALLOW)

        assert _admits(config, tmp_path) is True

    def test_a_rule_that_asks_is_a_refusal_because_nobody_can_be_asked(self, tmp_path: Path) -> None:
        config = _with_rule(build_channel_security_config("web_chat", local_mode=True), PermissionAction.ASK)

        assert _admits(config, tmp_path) is False
