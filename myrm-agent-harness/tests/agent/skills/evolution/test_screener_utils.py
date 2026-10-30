"""Tests for the screener's text helpers."""

from myrm_agent_harness.agent.skills.evolution.pipeline.confirmation import (
    extract_error_signals,
    parse_confirmation_response,
)


def test_extract_error_signals():
    error_log = "HTTP 404 timeout ValueError connection"
    signals = extract_error_signals(error_log)
    assert "404" in signals["http_status"]
    assert "ValueError" in signals["exception_types"]
    assert "timeout" in signals["error_keywords"]
    assert "connection" in signals["error_keywords"]


def test_parse_llm_response():

    dec, reason, conf = parse_confirmation_response("YES\nReason: fix it")
    assert dec is True
    assert "fix it" in reason

    dec, reason, conf = parse_confirmation_response("NO\nReason: too hard")
    assert dec is False
    assert "too hard" in reason

    dec, reason, conf = parse_confirmation_response('{"approved": true, "reason": "ok", "confidence": 0.9}')
    assert dec is True
    assert reason == "ok"
    assert conf == 0.9

    dec, reason, conf = parse_confirmation_response("CONFIRMED it's good")
    assert dec is True
    assert "good" in reason

    dec, reason, conf = parse_confirmation_response("REJECTED it's bad")
    assert dec is False
    assert "bad" in reason
