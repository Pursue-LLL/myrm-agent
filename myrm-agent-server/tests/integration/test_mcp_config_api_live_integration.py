"""Live API integration: MCP config PUT/GET roundtrip on running backend (:8080)."""

from __future__ import annotations

import sys
import time

import httpx
import pytest

_API_BASE = "http://127.0.0.1:8080"
_PROBE_NAME = "cap-surface-api-probe"


def _require_live_backend() -> None:
    try:
        resp = httpx.get(f"{_API_BASE}/api/v1/health", timeout=10.0)
    except (httpx.ConnectError, httpx.TimeoutException) as exc:
        pytest.skip(f"live backend unavailable at {_API_BASE}: {exc}")
    if resp.status_code != 200:
        pytest.skip(f"live backend unhealthy: {resp.status_code}")


def _get_mcp_record() -> dict[str, object]:
    resp = httpx.get(f"{_API_BASE}/api/v1/config/mcpServers", timeout=15.0)
    resp.raise_for_status()
    payload = resp.json()
    assert isinstance(payload, dict)
    return payload


def _put_mcp_configs(configs: list[dict[str, object]]) -> dict[str, object]:
    record = _get_mcp_record()
    version = str(record.get("version") or "0")
    resp = httpx.put(
        f"{_API_BASE}/api/v1/config/mcpServers",
        json={
            "deviceId": "web",
            "expectedVersion": version,
            "value": {"mcpConfigs": configs},
        },
        timeout=30.0,
    )
    resp.raise_for_status()
    body = resp.json()
    assert isinstance(body, dict)
    return body


def _list_server_names() -> list[str]:
    record = _get_mcp_record()
    value = record.get("value")
    if not isinstance(value, dict):
        return []
    configs = value.get("mcpConfigs")
    if not isinstance(configs, list):
        return []
    names: list[str] = []
    for item in configs:
        if isinstance(item, dict) and isinstance(item.get("name"), str):
            names.append(item["name"])
    return names


@pytest.mark.integration
def test_live_mcp_config_put_get_roundtrip() -> None:
    """Real PUT/GET /config/mcpServers persists probe server on live :8080 backend."""
    _require_live_backend()
    original_names = _list_server_names()

    probe = {
        "name": _PROBE_NAME,
        "type": "stdio",
        "command": sys.executable,
        "args": ["-c", "pass"],
        "description": "Capability surface live API integration probe",
        "enabled": True,
        "headers": {},
        "extra_params": {},
    }

    try:
        _put_mcp_configs([probe])
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            if _PROBE_NAME in _list_server_names():
                break
            time.sleep(0.3)
        else:
            raise AssertionError(f"probe server {_PROBE_NAME!r} not persisted via live API")

        record = _get_mcp_record()
        value = record.get("value")
        assert isinstance(value, dict)
        configs = value.get("mcpConfigs")
        assert isinstance(configs, list)
        match = next(
            (item for item in configs if isinstance(item, dict) and item.get("name") == _PROBE_NAME),
            None,
        )
        assert match is not None
        assert match.get("enabled") is True
    finally:
        if _PROBE_NAME in _list_server_names():
            restored = [name for name in original_names if name != _PROBE_NAME]
            if restored != original_names:
                configs = []
                record = _get_mcp_record()
                value = record.get("value")
                if isinstance(value, dict):
                    raw = value.get("mcpConfigs")
                    if isinstance(raw, list):
                        configs = [item for item in raw if isinstance(item, dict) and item.get("name") != _PROBE_NAME]
                _put_mcp_configs(configs)
