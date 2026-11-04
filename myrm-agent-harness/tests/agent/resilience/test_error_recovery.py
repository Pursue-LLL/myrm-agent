"""Tests for ErrorSelfCorrectionGovernor and hypothesis generation."""

import pytest

from myrm_agent_harness.agent.resilience.error_recovery import (
    ErrorSelfCorrectionGovernor,
)
from myrm_agent_harness.agent.resilience.types import RecoveryActionType
from myrm_agent_harness.toolkits.code_execution.python_extractor import SKILLS_NAMESPACE_ADVICE


def test_generate_hypotheses_missing_module():
    governor = ErrorSelfCorrectionGovernor(max_recovery_attempts=2)
    hypotheses = governor.generate_hypotheses(
        operation="run_script",
        target="script.py",
        error_message="ModuleNotFoundError: No module named 'httpx'",
        attempt=1,
    )
    assert len(hypotheses) >= 1
    primary = hypotheses[0]
    assert primary.action_type == RecoveryActionType.ENV_REPAIR
    assert "httpx" in primary.root_cause_guess


def test_generate_hypotheses_file_not_found():
    governor = ErrorSelfCorrectionGovernor(max_recovery_attempts=2)
    hypotheses = governor.generate_hypotheses(
        operation="read_file",
        target="/tmp/test.txt",
        error_message="FileNotFoundError: [Errno 2] No such file or directory: '/tmp/test.txt'",
        attempt=1,
    )
    assert len(hypotheses) >= 1
    assert hypotheses[0].action_type == RecoveryActionType.SANITIZE_INPUT


def test_generate_hypotheses_escalate_on_max_attempts():
    governor = ErrorSelfCorrectionGovernor(max_recovery_attempts=2)
    hypotheses = governor.generate_hypotheses(
        operation="run_cmd",
        target="cmd",
        error_message="Some fatal error",
        attempt=3,
    )
    assert len(hypotheses) == 1
    assert hypotheses[0].action_type == RecoveryActionType.ESCALATE


def test_diagnose_and_suggest_repair_format():
    governor = ErrorSelfCorrectionGovernor(max_recovery_attempts=2)
    outcome = governor.diagnose_and_suggest_repair(
        operation="fetch_url",
        target="https://api.example.com",
        error_message="ConnectionError: 504 Gateway Time-out",
        attempt=1,
        prior_actions=["initial_fetch"],
    )
    assert outcome.success is True
    assert outcome.action_taken == RecoveryActionType.RETRY
    assert "Diagnosed Cause" in outcome.diagnostic_details
    assert "504 Gateway Time-out" in outcome.original_error


def test_bare_skills_import_is_not_diagnosed_as_missing_dependency():
    governor = ErrorSelfCorrectionGovernor(max_recovery_attempts=2)
    outcome = governor.diagnose_and_suggest_repair(
        operation="bash_code_execute_tool",
        target='python3 -c "import skills"',
        error_message="Traceback (most recent call last):\nModuleNotFoundError: No module named 'skills'",
    )
    assert outcome.action_taken == RecoveryActionType.SANITIZE_INPUT
    assert SKILLS_NAMESPACE_ADVICE in outcome.diagnostic_details


@pytest.mark.parametrize("module", ["skills_extra", "skills.k8s_skill", "my_skills", "httpx"])
def test_other_missing_modules_keep_dependency_diagnosis(module: str):
    governor = ErrorSelfCorrectionGovernor(max_recovery_attempts=2)
    hypotheses = governor.generate_hypotheses(
        operation="run_script",
        target="script.py",
        error_message=f"ModuleNotFoundError: No module named '{module}'",
    )
    assert hypotheses[0].action_type == RecoveryActionType.ENV_REPAIR
