"""Live API integration: MCP config PUT/GET roundtrip on running shared dev backend."""

from __future__ import annotations

import sys
import time

import httpx
import pytest
from e2e_core.dev_ports import shared_api_base

_API_BASE = shared_api_base()
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


def _list_mcp_configs() -> list[dict[str, object]]:
    value = _get_mcp_record().get("value")
    if not isinstance(value, dict):
        return []
    configs = value.get("mcpConfigs")
    if not isinstance(configs, list):
        return []
    return [item for item in configs if isinstance(item, dict)]


def _find_probe() -> dict[str, object] | None:
    return next((item for item in _list_mcp_configs() if item.get("name") == _PROBE_NAME), None)


@pytest.mark.e2e
def test_live_mcp_config_put_get_roundtrip() -> None:
    """Real PUT/GET /config/mcpServers persists a probe server on the live shared dev backend, then puts the original list back.

    The PUT replaces the whole list, so the probe is appended to the servers already configured
    and the configuration read before the test is written back whatever the outcome.
    """
    _require_live_backend()
    original_configs = _list_mcp_configs()

    probe: dict[str, object] = {
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
        _put_mcp_configs([*(item for item in original_configs if item.get("name") != _PROBE_NAME), probe])
        deadline = time.monotonic() + 20.0
        while time.monotonic() < deadline:
            persisted = _find_probe()
            if persisted is not None:
                break
            time.sleep(0.3)
        else:
            raise AssertionError(f"probe server {_PROBE_NAME!r} not persisted via live API")

        assert persisted.get("enabled") is True
    finally:
        _put_mcp_configs(original_configs)
