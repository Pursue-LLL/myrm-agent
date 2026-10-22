"""测试无人值守与多渠道运行事件日志覆盖健康检查 API."""

from fastapi.testclient import TestClient
import pytest

from app.api.system.unattended_coverage_api import router as coverage_router
from fastapi import FastAPI


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(coverage_router, prefix="/api/v1/system")
    return TestClient(app)


def test_get_coverage_summary(client: TestClient) -> None:
    """测试获取覆盖状态大盘."""
    resp = client.get("/api/v1/system/event-log-coverage/summary")
    assert resp.status_code == 200
    data = resp.json()

    assert "is_directory_configured" in data
    assert "entrypoints" in data
    assert data["anti_growth_protection"] is True
    assert "shards" in data

    entrypoints = {ep["entrypoint"]: ep for ep in data["entrypoints"]}
    assert "cron" in entrypoints
    assert "channel" in entrypoints
    assert "goal" in entrypoints
    assert "voice" in entrypoints
    assert "voice_realtime" in entrypoints
    assert "web_chat" in entrypoints

    # 验证全部受管入口均已标记注入且样本标识安全
    for ep in entrypoints.values():
        assert ep["is_injected"] is True
        assert ep["is_safe"] is True


def test_validate_session_id(client: TestClient) -> None:
    """测试校验指定入口会话标识."""
    # 1. 校验 cron 入口
    resp_cron = client.post(
        "/api/v1/system/event-log-coverage/validate",
        json={"entrypoint": "cron", "raw_identifier": "backup_db"},
    )
    assert resp_cron.status_code == 200
    d_cron = resp_cron.json()
    assert d_cron["is_safe"] is True
    assert d_cron["is_daily_sharded"] is True
    assert d_cron["resolved_session_id"].startswith("cron:backup_db:")

    # 2. 校验 channel 入口非法字符过滤
    resp_chan = client.post(
        "/api/v1/system/event-log-coverage/validate",
        json={"entrypoint": "channel", "raw_identifier": "tg/channel/unsafe"},
    )
    assert resp_chan.status_code == 200
    d_chan = resp_chan.json()
    assert d_chan["is_safe"] is True
    assert "/" not in d_chan["resolved_session_id"]

    # 3. 校验 voice_realtime 入口
    resp_rt = client.post(
        "/api/v1/system/event-log-coverage/validate",
        json={"entrypoint": "voice_realtime", "raw_identifier": "realtime-tool"},
    )
    assert resp_rt.status_code == 200
    d_rt = resp_rt.json()
    assert d_rt["is_safe"] is True
    assert d_rt["is_daily_sharded"] is True
    assert d_rt["resolved_session_id"].startswith("voice:realtime:")
