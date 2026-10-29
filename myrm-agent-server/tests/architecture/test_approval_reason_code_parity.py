"""Approval reason codes: the engine's codes and the codes the web card has copy for must agree.

[POS]
tests/architecture/test_approval_reason_code_parity.py

[INPUT]
- myrm_agent_harness agent.security.approval_reason: `ApprovalReasonCode`
- myrm-agent-frontend approvalReasonCode.ts: `APPROVAL_REASON_CODES`

[OUTPUT]
- Fails when the engine can send a code the web card has no copy for (the card would show the English text)
- Fails when the frontend lists a code the engine never sends (dead locale strings)
"""

from __future__ import annotations

import re

import pytest
from myrm_agent_harness.agent.security.approval_reason import ApprovalReasonCode

from tests.support.frontend_api_paths import FRONTEND_SRC

_FRONTEND_CODES = FRONTEND_SRC / "lib" / "approval" / "approvalReasonCode.ts"

_CODES_RE = re.compile(r"APPROVAL_REASON_CODES\s*=\s*\[(?P<body>.*?)\]\s*as const", re.DOTALL)
_QUOTED_RE = re.compile(r"'([a-z_]+)'")


def _frontend_codes() -> set[str]:
    match = _CODES_RE.search(_FRONTEND_CODES.read_text(encoding="utf-8"))
    assert match, f"APPROVAL_REASON_CODES list not found in {_FRONTEND_CODES}"
    return set(_QUOTED_RE.findall(match.group("body")))


@pytest.mark.skipif(not _FRONTEND_CODES.is_file(), reason="frontend sources are not part of this checkout")
def test_approval_reason_codes_match_between_engine_and_web_card() -> None:
    engine = {code.value for code in ApprovalReasonCode}
    frontend = _frontend_codes()

    assert not engine - frontend, (
        f"The engine sends reason codes the web card has no copy for (add them to approvalReasonCode.ts and the six "
        f"locales): {sorted(engine - frontend)}"
    )
    assert not frontend - engine, (
        f"approvalReasonCode.ts lists codes the engine never sends (remove them and their locale strings): "
        f"{sorted(frontend - engine)}"
    )
