"""Unit tests for auth alert engine (anomaly detection + dedup + notification)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.middleware.auth_alert import (
    AuthAlert,
    _dedup_key,
    evaluate_auth_anomalies,
)


@pytest.fixture
def tmp_audit_file(tmp_path: Path) -> Path:
    return tmp_path / "auth_audit.jsonl"


@pytest.fixture(autouse=True)
def _patch_audit_file(tmp_audit_file: Path):
    with patch("app.middleware.auth_alert.AUDIT_LOG_FILE", tmp_audit_file):
        yield


def _write_events(path: Path, events: list[dict[str, object]]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for event in events:
            f.write(json.dumps(event) + "\n")


def _failure_event(ip: str, ts: float | None = None) -> dict[str, object]:
    return {"ts": ts or time.time(), "type": "auth_failure", "ip": ip}


def _success_event(ip: str, ts: float | None = None) -> dict[str, object]:
    return {"ts": ts or time.time(), "type": "auth_success", "ip": ip, "source": "sandbox_api_key"}


class TestDedupKey:
    def test_basic(self):
        alert = AuthAlert(
            alert_type="high_failure_rate_ip",
            severity="high",
            message="test",
            target_ip="1.2.3.4",
            failure_count=10,
        )
        assert _dedup_key(alert) == "high_failure_rate_ip:1.2.3.4"

    def test_different_ips(self):
        a1 = AuthAlert("high_failure_rate_ip", "high", "m1", "1.1.1.1", 10)
        a2 = AuthAlert("high_failure_rate_ip", "high", "m2", "2.2.2.2", 10)
        assert _dedup_key(a1) != _dedup_key(a2)


class TestEvaluateAuthAnomalies:
    @pytest.mark.asyncio
    async def test_no_file(self, tmp_audit_file: Path):
        assert not tmp_audit_file.exists()
        alerts = await evaluate_auth_anomalies()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_empty_file(self, tmp_audit_file: Path):
        tmp_audit_file.write_text("")
        alerts = await evaluate_auth_anomalies()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_below_threshold(self, tmp_audit_file: Path):
        events = [_failure_event("1.1.1.1") for _ in range(9)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_at_threshold(self, tmp_audit_file: Path):
        events = [_failure_event("1.1.1.1") for _ in range(10)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert len(alerts) == 1
        assert alerts[0].target_ip == "1.1.1.1"
        assert alerts[0].failure_count == 10

    @pytest.mark.asyncio
    async def test_above_threshold(self, tmp_audit_file: Path):
        events = [_failure_event("1.1.1.1") for _ in range(25)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert len(alerts) == 1
        assert alerts[0].failure_count == 25

    @pytest.mark.asyncio
    async def test_multiple_ips(self, tmp_audit_file: Path):
        events = [_failure_event("1.1.1.1") for _ in range(15)]
        events += [_failure_event("2.2.2.2") for _ in range(12)]
        events += [_failure_event("3.3.3.3") for _ in range(5)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        alert_ips = {a.target_ip for a in alerts}
        assert "1.1.1.1" in alert_ips
        assert "2.2.2.2" in alert_ips
        assert "3.3.3.3" not in alert_ips

    @pytest.mark.asyncio
    async def test_old_events_ignored(self, tmp_audit_file: Path):
        old_ts = time.time() - 7200
        events = [_failure_event("1.1.1.1", ts=old_ts) for _ in range(20)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_success_events_not_counted(self, tmp_audit_file: Path):
        events = [_success_event("1.1.1.1") for _ in range(20)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_corrupted_line_skipped(self, tmp_audit_file: Path):
        events = [_failure_event("1.1.1.1") for _ in range(10)]
        _write_events(tmp_audit_file, events)
        with tmp_audit_file.open("a") as f:
            f.write("THIS IS NOT JSON\n")
            for _ in range(5):
                f.write(json.dumps(_failure_event("1.1.1.1")) + "\n")

        alerts = await evaluate_auth_anomalies()
        assert len(alerts) == 1
        assert alerts[0].failure_count == 15

    @pytest.mark.asyncio
    async def test_file_permission_error(self, tmp_audit_file: Path):
        tmp_audit_file.write_text("data")
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            alerts = await evaluate_auth_anomalies()
        assert alerts == []

    @pytest.mark.asyncio
    async def test_alert_type_and_severity(self, tmp_audit_file: Path):
        events = [_failure_event("10.0.0.1") for _ in range(10)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert alerts[0].alert_type == "high_failure_rate_ip"
        assert alerts[0].severity == "high"

    @pytest.mark.asyncio
    async def test_alert_message_contains_ip(self, tmp_audit_file: Path):
        events = [_failure_event("192.168.1.50") for _ in range(10)]
        _write_events(tmp_audit_file, events)
        alerts = await evaluate_auth_anomalies()
        assert "192.168.1.50" in alerts[0].message


class TestPersistAlert:
    @pytest.mark.asyncio
    async def test_persist_calls_notification_service(self):
        from app.middleware.auth_alert import _persist_alert

        alert = AuthAlert("high_failure_rate_ip", "high", "test msg", "1.1.1.1", 15)

        mock_create = AsyncMock(return_value="notif-123")
        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            mock_create,
        ):
            await _persist_alert(alert)

        mock_create.assert_called_once()
        call_kwargs = mock_create.call_args
        assert call_kwargs.kwargs.get("type") or call_kwargs[1].get("type") == "warning"

    @pytest.mark.asyncio
    async def test_persist_error_does_not_raise(self):
        from app.middleware.auth_alert import _persist_alert

        alert = AuthAlert("high_failure_rate_ip", "high", "test", "1.1.1.1", 10)

        with patch(
            "app.services.infra.system_notification.SystemNotificationService.create_notification",
            AsyncMock(side_effect=Exception("db error")),
        ):
            await _persist_alert(alert)
