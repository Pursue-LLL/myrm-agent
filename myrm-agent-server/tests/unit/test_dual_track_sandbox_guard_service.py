"""Unit test for DualTrackSandboxGuardService.

[INPUT]
- EvaluateExecutionRequest, RegisterRedlineRuleRequest.

[OUTPUT]
- Verified behavior of file and command interception, rule registration, and policy compilation.

[POS]
- Server unit test layer for dual-track soft memory vs hard redline sandbox guard.
"""

from __future__ import annotations

import base64

from app.schemas.dual_track_sandbox_guard import (
    EvaluateExecutionRequest,
    RegisterRedlineRuleRequest,
)
from app.services.security.dual_track_sandbox_guard_service import (
    DualTrackSandboxGuardService,
)


def test_service_evaluate_file_access() -> None:
    service = DualTrackSandboxGuardService()

    # 1. Blocked protected file (.env)
    req_env = EvaluateExecutionRequest(
        operation_type="file",
        target=".env",
        sub_operation="read",
    )
    res_env = service.evaluate_execution(req_env)
    assert res_env.is_permitted is False
    assert res_env.verdict == "BLOCKED_HARD_REDLINE_FILE"
    assert res_env.blocked_by_rule_id == "RL-FILE-001"

    # 2. Blocked certificate (.pem)
    req_pem = EvaluateExecutionRequest(
        operation_type="file",
        target="certs/server.pem",
        sub_operation="read",
    )
    res_pem = service.evaluate_execution(req_pem)
    assert res_pem.is_permitted is False
    assert res_pem.verdict == "BLOCKED_HARD_REDLINE_FILE"

    # 3. Permitted normal source file
    req_safe = EvaluateExecutionRequest(
        operation_type="file",
        target="src/index.ts",
        sub_operation="write",
    )
    res_safe = service.evaluate_execution(req_safe)
    assert res_safe.is_permitted is True
    assert res_safe.verdict == "PERMITTED"


def test_service_evaluate_command_execution() -> None:
    service = DualTrackSandboxGuardService()

    # 1. Destructive rm -rf /
    req_rm = EvaluateExecutionRequest(
        operation_type="command",
        target="rm -rf /",
    )
    res_rm = service.evaluate_execution(req_rm)
    assert res_rm.is_permitted is False
    assert res_rm.verdict == "BLOCKED_HARD_REDLINE_COMMAND"

    # 2. Direct cat .env
    req_cat = EvaluateExecutionRequest(
        operation_type="command",
        target="cat .env",
    )
    res_cat = service.evaluate_execution(req_cat)
    assert res_cat.is_permitted is False
    assert res_cat.verdict == "BLOCKED_HARD_REDLINE_FILE"

    # 3. Obfuscated base64 evasion
    encoded = base64.b64encode(b"grep -i token .env").decode("ascii")
    req_evasion = EvaluateExecutionRequest(
        operation_type="command",
        target=f"echo '{encoded}' | base64 -d | bash",
    )
    res_evasion = service.evaluate_execution(req_evasion)
    assert res_evasion.is_permitted is False
    assert res_evasion.verdict == "BLOCKED_EVASION_ATTEMPT"

    # 4. Permitted benign command
    req_safe = EvaluateExecutionRequest(
        operation_type="command",
        target="git status",
    )
    res_safe = service.evaluate_execution(req_safe)
    assert res_safe.is_permitted is True
    assert res_safe.verdict == "PERMITTED"


def test_service_register_rule_and_compile() -> None:
    service = DualTrackSandboxGuardService()

    initial_policy = service.get_compiled_policy()
    initial_count = initial_policy.rule_count

    # Register custom rule
    reg_req = RegisterRedlineRuleRequest(
        rule_id="RL-FILE-888",
        category="FILE_PROTECTION",
        pattern="**/*.bak_key",
        description="Block backup key files",
        severity="HIGH",
    )
    rule_dto = service.register_rule(reg_req)
    assert rule_dto.rule_id == "RL-FILE-888"

    updated_policy = service.get_compiled_policy()
    assert updated_policy.rule_count == initial_count + 1
    assert "**/*.bak_key" in updated_policy.blocked_file_patterns
