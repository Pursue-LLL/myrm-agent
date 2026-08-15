"""Connect doctor 真实文件校验链路集成测试。

关键路径（verify_connector_config 读盘→定位 myrm-memory→提取 Bearer→哈希比对）
全程真实执行，不做 mock。仅做两处环境控制：
- ``is_local_mode`` → LOCAL 部署开关（测试环境须显式指定部署模式）；
- ``PROFILES["cursor"].config_file_path`` → 注入临时目录，避免触碰真实用户配置文件。

覆盖正常（verified）、失败（config_file_missing / entry_missing / token_mismatch）、
边界（token_env 环境变量盲区）四条路径。
"""

import json
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.services.connect.profiles import PROFILES
from tests.support.minimal_app import build_minimal_app

_app = build_minimal_app(preset="connect")
API_PREFIX = "/api/v1"


@pytest.fixture
def local_client(tmp_path: Path) -> Iterator[TestClient]:
    """LOCAL 模式客户端：真实文件校验链路，cursor 配置注入临时目录。"""
    import app.services.connect.service as svc

    svc._service = None
    cursor = replace(PROFILES["cursor"], config_file_path=str(tmp_path / "cursor_mcp.json"))
    profiles = {**PROFILES, "cursor": cursor}
    with (
        patch("app.core.security.auth.identity.is_loopback_ip", return_value=True),
        patch("app.services.connect.service.is_local_mode", return_value=True),
        patch("app.services.connect.service.PROFILES", profiles),
    ):
        yield TestClient(_app)


def _write_cursor_config(tmp_path: Path, payload: dict[str, object]) -> None:
    (tmp_path / "cursor_mcp.json").write_text(json.dumps(payload), encoding="utf-8")


class TestDoctorRealFileVerification:
    def test_verified_when_config_matches(self, local_client: TestClient, tmp_path: Path):
        token = local_client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"}).json()["token"]
        _write_cursor_config(
            tmp_path,
            {
                "mcpServers": {
                    "myrm-memory": {
                        "url": "http://127.0.0.1:8080/mcp",
                        "transport": "streamable-http",
                        "headers": {"Authorization": f"Bearer {token}"},
                    }
                }
            },
        )
        data = local_client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"}).json()
        assert data["healthy"] is True
        assert data["detail"] == "verified"
        assert data["severity"] == "ok"

    def test_missing_config_file(self, local_client: TestClient):
        data = local_client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"}).json()
        assert data["healthy"] is False
        assert data["detail"] == "config_file_missing"
        assert data["severity"] == "error"

    def test_entry_missing(self, local_client: TestClient, tmp_path: Path):
        local_client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"})
        _write_cursor_config(tmp_path, {"mcpServers": {"other-agent": {}}})
        data = local_client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"}).json()
        assert data["healthy"] is False
        assert data["detail"] == "entry_missing"
        assert data["severity"] == "error"

    def test_token_mismatch(self, local_client: TestClient, tmp_path: Path):
        local_client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"})
        _write_cursor_config(
            tmp_path,
            {"mcpServers": {"myrm-memory": {"headers": {"Authorization": "Bearer stale_token_abc"}}}},
        )
        data = local_client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"}).json()
        assert data["healthy"] is False
        assert data["detail"] == "token_mismatch"
        assert data["severity"] == "error"

    def test_env_token_placeholder_is_warn(self, local_client: TestClient, tmp_path: Path):
        local_client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"})
        _write_cursor_config(
            tmp_path,
            {"mcpServers": {"myrm-memory": {"headers": {"Authorization": "Bearer ${MYRM_MCP_TOKEN}"}}}},
        )
        data = local_client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"}).json()
        assert data["healthy"] is False
        assert data["detail"] == "token_env"
        assert data["severity"] == "warn"

    def test_status_persists_verified_detail(self, local_client: TestClient, tmp_path: Path):
        token = local_client.post(f"{API_PREFIX}/connect/generate", json={"profile_id": "cursor"}).json()["token"]
        _write_cursor_config(
            tmp_path,
            {"mcpServers": {"myrm-memory": {"headers": {"Authorization": f"Bearer {token}"}}}},
        )
        local_client.post(f"{API_PREFIX}/connect/doctor", json={"profile_id": "cursor"})
        status = local_client.get(f"{API_PREFIX}/connect/status").json()
        item = next(i for i in status if i["profile_id"] == "cursor")
        assert item["doctor_ok"] is True
        assert item["last_doctor_detail"] == "verified"
        assert item["last_doctor_at"] is not None
        assert item["connected_at"] is None
