"""POST /config/privacy-preview: the settings page tries a sentence against the rules in its form."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

client = TestClient(build_minimal_app(preset="config"))

_URL = "/api/v1/config/privacy-preview"
_SENTENCE = "帮我总结凤凰计划Q3预算超支原因，发给李总"


def _preview(**fields: object) -> dict[str, object]:
    response = client.post(_URL, json={"text": _SENTENCE, **fields})
    assert response.status_code == 200, response.text
    body: dict[str, object] = response.json()
    return body


def test_an_s3_keyword_is_masked_with_the_default_action() -> None:
    assert _preview(privacy_custom_keywords_s3=["凤凰计划"]) == {
        "level": "s3",
        "action": "redact",
        "model_sees": "帮我总结[REDACTED] [PII:custom]Q3预算超支原因，发给李总",
        "ineffective_patterns": [],
    }


def test_an_s2_keyword_is_only_warned_about_by_default() -> None:
    assert _preview(privacy_custom_keywords_s2=["凤凰计划"]) == {
        "level": "s2",
        "action": "warn",
        "model_sees": _SENTENCE,
        "ineffective_patterns": [],
    }


def test_the_action_in_the_request_wins() -> None:
    data = _preview(privacy_s3_action="pseudonymize", privacy_custom_keywords_s3=["凤凰计划"])

    assert data["action"] == "pseudonymize"
    assert data["model_sees"] == "帮我总结<CUSTOM_KEYWORD_1>Q3预算超支原因，发给李总"


def test_a_blocking_action_means_the_model_sees_nothing() -> None:
    data = _preview(privacy_s3_action="block", privacy_custom_keywords_s3=["凤凰计划"])

    assert data == {"level": "s3", "action": "block", "model_sees": None, "ineffective_patterns": []}


def test_a_pattern_rule_is_applied() -> None:
    data = client.post(
        _URL,
        json={"text": "员工 EMP-123456 离职", "privacy_s3_action": "redact", "privacy_custom_patterns_s3": [r"EMP-\d{6}"]},
    ).json()

    assert data["model_sees"] == "员工 [REDACTED] [PII:custom] 离职"


def test_a_text_with_nothing_sensitive_is_reported_as_such() -> None:
    data = client.post(_URL, json={"text": "今天天气不错", "privacy_custom_keywords_s3": ["凤凰计划"]}).json()

    assert data == {"level": "s1", "action": None, "model_sees": "今天天气不错", "ineffective_patterns": []}


def test_an_unknown_action_is_rejected() -> None:
    response = client.post(_URL, json={"text": _SENTENCE, "privacy_s3_action": "shred"})

    assert response.status_code == 422


def test_an_oversized_text_is_rejected() -> None:
    assert client.post(_URL, json={"text": "a" * 4001}).status_code == 422


def test_a_unicode_property_pattern_masks_chinese_text() -> None:
    data = client.post(
        _URL,
        json={"text": "客户：星河科技已确认", "privacy_custom_patterns_s3": [r"\p{Han}{2,4}科技"]},
    ).json()

    assert data["model_sees"] == "客户：[REDACTED] [PII:custom]已确认"
    assert data["ineffective_patterns"] == []


def test_a_pattern_that_cannot_match_is_named() -> None:
    data = _preview(privacy_custom_keywords_s3=["凤凰计划"], privacy_custom_patterns_s3=["([", r"EMP-\d{6}"])

    assert data["ineffective_patterns"] == ["(["]
    assert data["model_sees"] == "帮我总结[REDACTED] [PII:custom]Q3预算超支原因，发给李总"


def test_a_pattern_too_large_to_build_is_named_and_does_not_take_the_server_down() -> None:
    data = _preview(privacy_custom_patterns_s3=[r"\d{99999999}", r"EMP-\d{6}"])

    assert data["ineffective_patterns"] == [r"\d{99999999}"]


def test_the_patterns_that_cannot_match_are_named_without_a_sentence() -> None:
    response = client.post(_URL, json={"text": "", "privacy_custom_patterns_s2": ["(["], "privacy_custom_patterns_s3": []})

    assert response.status_code == 200
    assert response.json() == {"level": "s1", "action": None, "model_sees": "", "ineffective_patterns": ["(["]}


def test_as_many_rules_as_a_chat_turn_accepts_are_applied() -> None:
    keywords = [f"codename{n}" for n in range(300)] + ["凤凰计划"]
    data = _preview(privacy_custom_keywords_s3=keywords, privacy_custom_patterns_s3=["x" * 600])

    assert data["level"] == "s3"
    assert "凤凰计划" not in str(data["model_sees"])
