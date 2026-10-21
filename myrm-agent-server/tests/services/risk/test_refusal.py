"""The refusal a REST client gets for text a risk rule holds: its payload, and which texts are screened together."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from app.services.risk.detection import _CompiledRule, compile_pattern
from app.services.risk.refusal import RISK_HELD_CODE, reject_if_risky, risk_rules_payload
from tests.support.risk_gate import API_KEY_RULE, SECRET, build_service_with_rules

from .conftest import EngineBuilder

_DETECTION = "app.services.risk.detection.get_detection_service"
_ASSIGNMENT_RULE = _CompiledRule(
    rule_id="r-assign",
    display_name="Credential Assignment",
    severity="high",
    category="credential",
    compiled=compile_pattern(r"password\s*=\s*\S{6,}"),
)


async def test_a_held_text_raises_the_coded_refusal_without_the_text() -> None:
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        with pytest.raises(HTTPException) as refusal:
            await reject_if_risky("fine", f"key {SECRET}", session_id="chat-1")

    assert refusal.value.status_code == 400
    assert refusal.value.detail == {
        "code": RISK_HELD_CODE,
        "message": "Text held by a risk rule",
        "rules": [{"rule_id": "r-apikey", "display_name": "API Key Leak", "severity": "critical"}],
    }
    assert SECRET not in str(refusal.value.detail)


@pytest.mark.parametrize("texts", [(), (None,), ("",), ("only keep the 2026 rows", None)])
async def test_texts_without_a_secret_pass(texts: tuple[str | None, ...]) -> None:
    with patch(_DETECTION, return_value=build_service_with_rules([API_KEY_RULE])):
        await reject_if_risky(*texts, session_id="chat-1")


async def test_fields_of_one_request_are_not_read_as_one_sentence() -> None:
    """A word in one field and a token in the next must not combine into an assignment the user never wrote."""
    service = build_service_with_rules([_ASSIGNMENT_RULE])

    with patch(_DETECTION, return_value=service):
        await reject_if_risky("reset the password", "= hunter2hunter2 is not a thing", session_id=None)
        with pytest.raises(HTTPException):
            await reject_if_risky("password = hunter2hunter2", session_id=None)


async def test_builtin_rule_payload_names_the_rule_but_never_the_secret(build_engine: EngineBuilder) -> None:
    service = await build_engine()
    result = service.detect("password: Zk9#mango42")

    (rule,) = risk_rules_payload(result)

    assert set(rule) == {"rule_id", "display_name", "severity"}
    assert rule["display_name"]
    assert "Zk9" not in str(rule)
