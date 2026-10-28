"""Lockout reporting: one WARNING per engaged lock, an audit event only where the deployment audits auth."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest
from starlette.requests import Request

from app.core.security.share.share_hmac import token_fingerprint
from app.services.audit.lockout_events import report_lockout, report_share_lockout

_TOKEN = "a-share-token.with-a-signature"


@pytest.fixture
def audit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "logs" / "auth_audit.jsonl"
    monkeypatch.setattr("app.middleware.auth_audit.AUDIT_LOG_FILE", path)
    return path


def _audit(monkeypatch: pytest.MonkeyPatch, *, enabled: bool) -> None:
    monkeypatch.setattr(
        "app.services.audit.lockout_events.get_deployment_capabilities",
        lambda: SimpleNamespace(enables_auth_audit=enabled),
    )


def _request(host: str | None) -> Request:
    client = SimpleNamespace(host=host) if host is not None else None
    return cast(Request, SimpleNamespace(client=client))


def _events(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def test_local_deployments_log_a_warning_and_keep_no_audit_file(
    audit_file: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _audit(monkeypatch, enabled=False)

    with caplog.at_level(logging.WARNING, logger="app.services.audit.lockout_events"):
        report_lockout("webui_login", client="10.0.0.1")

    assert [record.getMessage() for record in caplog.records] == ["Lockout engaged: scope=webui_login client=10.0.0.1 subject=-"]
    assert not audit_file.exists()


def test_audited_deployments_also_record_a_rate_limit_event(audit_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _audit(monkeypatch, enabled=True)

    report_lockout("webui_login", client="10.0.0.1")

    [event] = _events(audit_file)
    assert event["type"] == "rate_limit_exceeded"
    assert event["ip"] == "10.0.0.1"
    assert event["meta"] == {"scope": "webui_login"}


def test_share_lockouts_name_the_share_by_a_short_fingerprint_never_the_token(
    audit_file: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    _audit(monkeypatch, enabled=True)

    with caplog.at_level(logging.WARNING, logger="app.services.audit.lockout_events"):
        report_share_lockout(_request("203.0.113.9"), _TOKEN)

    fingerprint = token_fingerprint(_TOKEN)[:12]
    [event] = _events(audit_file)
    assert event["ip"] == "203.0.113.9"
    assert event["meta"] == {"scope": "share_password", "subject": fingerprint}
    assert f"subject={fingerprint}" in caplog.text
    assert _TOKEN not in caplog.text
    assert _TOKEN not in audit_file.read_text(encoding="utf-8")


def test_a_request_without_a_client_address_is_reported_as_unknown(audit_file: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _audit(monkeypatch, enabled=True)

    report_share_lockout(_request(None), _TOKEN)

    [event] = _events(audit_file)
    assert event["ip"] == "unknown"
