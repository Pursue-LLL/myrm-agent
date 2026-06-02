"""Unit tests for auth audit JSONL logger."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.middleware.auth_audit import AuthEventType, log_auth_event


@pytest.fixture
def tmp_audit_file(tmp_path: Path) -> Path:
    return tmp_path / "auth_audit.jsonl"


@pytest.fixture(autouse=True)
def _patch_audit_file(tmp_audit_file: Path):
    with patch("app.middleware.auth_audit.AUDIT_LOG_FILE", tmp_audit_file):
        with patch("app.middleware.auth_audit._rotator", None):
            yield


class TestAuthEventType:
    def test_enum_values(self):
        assert AuthEventType.AUTH_SUCCESS.value == "auth_success"
        assert AuthEventType.AUTH_FAILURE.value == "auth_failure"
        assert AuthEventType.RATE_LIMIT_EXCEEDED.value == "rate_limit_exceeded"

    def test_enum_count(self):
        assert len(AuthEventType) == 3


class TestLogAuthEvent:
    def test_basic_success_event(self, tmp_audit_file: Path):
        log_auth_event(AuthEventType.AUTH_SUCCESS, "10.0.0.1", auth_source="sandbox_api_key")

        lines = tmp_audit_file.read_text().strip().split("\n")
        assert len(lines) == 1
        event = json.loads(lines[0])
        assert event["type"] == "auth_success"
        assert event["ip"] == "10.0.0.1"
        assert event["source"] == "sandbox_api_key"
        assert "ts" in event

    def test_failure_event_with_metadata(self, tmp_audit_file: Path):
        log_auth_event(
            AuthEventType.AUTH_FAILURE,
            "192.168.1.100",
            metadata={"path": "/api/v1/chats"},
        )

        lines = tmp_audit_file.read_text().strip().split("\n")
        event = json.loads(lines[0])
        assert event["type"] == "auth_failure"
        assert event["ip"] == "192.168.1.100"
        assert event["meta"]["path"] == "/api/v1/chats"
        assert "source" not in event

    def test_multiple_events_appended(self, tmp_audit_file: Path):
        log_auth_event(AuthEventType.AUTH_SUCCESS, "1.1.1.1", auth_source="sandbox_api_key")
        log_auth_event(AuthEventType.AUTH_FAILURE, "2.2.2.2")
        log_auth_event(AuthEventType.AUTH_SUCCESS, "3.3.3.3", auth_source="sandbox_api_key")

        lines = tmp_audit_file.read_text().strip().split("\n")
        assert len(lines) == 3

    def test_creates_parent_directory(self, tmp_path: Path):
        nested = tmp_path / "deep" / "nested" / "audit.jsonl"
        with patch("app.middleware.auth_audit.AUDIT_LOG_FILE", nested):
            log_auth_event(AuthEventType.AUTH_SUCCESS, "1.1.1.1", auth_source="test")
        assert nested.exists()

    def test_no_source_when_none(self, tmp_audit_file: Path):
        log_auth_event(AuthEventType.AUTH_FAILURE, "1.1.1.1")

        event = json.loads(tmp_audit_file.read_text().strip())
        assert "source" not in event

    def test_no_meta_when_none(self, tmp_audit_file: Path):
        log_auth_event(AuthEventType.AUTH_SUCCESS, "1.1.1.1", auth_source="test")

        event = json.loads(tmp_audit_file.read_text().strip())
        assert "meta" not in event

    def test_timestamp_is_numeric(self, tmp_audit_file: Path):
        log_auth_event(AuthEventType.AUTH_SUCCESS, "1.1.1.1", auth_source="test")

        event = json.loads(tmp_audit_file.read_text().strip())
        assert isinstance(event["ts"], float)
        assert event["ts"] > 0

    def test_write_error_does_not_raise(self, tmp_audit_file: Path):
        """Write failure should be swallowed (logged, not raised)."""
        tmp_audit_file.parent.mkdir(parents=True, exist_ok=True)
        tmp_audit_file.write_text("")
        original_open = tmp_audit_file.open

        def _failing_open(mode: str = "r", **kwargs: object):
            if "a" in mode:
                raise PermissionError("denied")
            return original_open(mode, **kwargs)

        with patch.object(type(tmp_audit_file), "open", side_effect=_failing_open):
            log_auth_event(AuthEventType.AUTH_FAILURE, "1.1.1.1")
