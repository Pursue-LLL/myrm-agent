"""Unit tests for GitLeakShieldService in server layer.

[POS]
Verifies server-level orchestration of pre-commit diff scanning, git commit command interception,
and egress log redaction.
"""

from __future__ import annotations

from app.schemas.git_leak_shield import (
    GitDiffScanRequest,
    PreCommitCheckRequest,
    RedactTextRequest,
)
from app.services.security.git_leak_shield_service import (
    GitLeakShieldService,
)


def test_git_leak_shield_service_scan_diff() -> None:
    service = GitLeakShieldService()

    # 1. Leaked diff
    leaked_diff = (
        "--- a/client.ts\n"
        "+++ b/client.ts\n"
        "@@ -1,3 +1,4 @@\n"
        "+const openAiKey = 'sk-proj-abcdef123456789012345678901234567890123456';\n"
    )
    res = service.scan_diff(GitDiffScanRequest(diff_content=leaked_diff, file_path="client.ts"))
    assert res.has_leak is True
    assert len(res.findings) == 1
    assert res.findings[0].suggested_env_var == "OPENAI_API_KEY"
    assert "****" in res.findings[0].masked_snippet

    # 2. Clean diff
    clean_diff = (
        "--- a/client.ts\n"
        "+++ b/client.ts\n"
        "@@ -1,3 +1,4 @@\n"
        "+const openAiKey = process.env.OPENAI_API_KEY;\n"
    )
    clean_res = service.scan_diff(GitDiffScanRequest(diff_content=clean_diff, file_path="client.ts"))
    assert clean_res.has_leak is False
    assert len(clean_res.findings) == 0


def test_git_leak_shield_service_check_commit_command() -> None:
    service = GitLeakShieldService()

    leaked_diff = (
        "--- a/repo.py\n"
        "+++ b/repo.py\n"
        "+TOKEN = 'ghp_123456789012345678901234567890123456'\n"
    )

    # 1. Blocked git commit
    block_req = PreCommitCheckRequest(
        command="git commit -m 'feat: secret leak'",
        diff_content=leaked_diff,
    )
    block_res = service.check_commit_command(block_req)
    assert block_res.blocked is True
    assert len(block_res.findings) == 1
    assert "credential(s) detected" in block_res.reason

    # 2. Permitted clean git commit
    clean_req = PreCommitCheckRequest(
        command="git commit -m 'feat: clean commit'",
        diff_content="+clean_code = True\n",
    )
    clean_res = service.check_commit_command(clean_req)
    assert clean_res.blocked is False
    assert len(clean_res.findings) == 0

    # 3. Non-commit command bypassed
    status_req = PreCommitCheckRequest(
        command="git status",
        diff_content=leaked_diff,
    )
    status_res = service.check_commit_command(status_req)
    assert status_res.blocked is False


def test_git_leak_shield_service_redact_egress() -> None:
    service = GitLeakShieldService()

    text = "Deploying with Stripe key sk_live_123456789012345678901234 to cluster"
    redact_res = service.redact_egress_text(RedactTextRequest(text=text))

    assert redact_res.redactions_count == 1
    assert "Stripe API Secret Key" in redact_res.detected_types
    assert "sk_live_123456789012345678901234" not in redact_res.redacted_text
    assert "****" in redact_res.redacted_text
