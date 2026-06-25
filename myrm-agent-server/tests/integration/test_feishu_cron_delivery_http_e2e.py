"""HTTP-level integration tests for cron webhook delivery (Feishu + generic).

Uses real local HTTP servers — no httpx.AsyncClient mock on delivery paths.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import ClassVar
from unittest.mock import patch

import pytest

from app.core.cron.adapters.channel_delivery import ChannelResultDelivery
from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery
from app.core.cron.adapters.feishu_bot_webhook import (
    deliver_feishu_bot_webhook,
    is_feishu_bot_hook_url,
)
from myrm_agent_harness.toolkits.cron.types import CronJob, DeliveryConfig, JobResult, JobType, Schedule


class _HookCaptureHandler(BaseHTTPRequestHandler):
    captured: ClassVar[dict[str, object]] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _HookCaptureHandler.captured = {
            "path": self.path,
            "body": body,
            "json": json.loads(body.decode("utf-8")),
            "headers": {k: v for k, v in self.headers.items()},
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"code":0,"msg":"success"}')

    def log_message(self, format: str, *args: object) -> None:
        return


class _GenericWebhookHandler(BaseHTTPRequestHandler):
    captured: ClassVar[dict[str, object]] = {}

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        _GenericWebhookHandler.captured = {
            "body": body,
            "json": json.loads(body.decode("utf-8")),
            "headers": {k: v for k, v in self.headers.items()},
        }
        self.send_response(200)
        self.end_headers()

    def log_message(self, format: str, *args: object) -> None:
        return


@pytest.fixture()
def generic_webhook_url() -> str:
    _GenericWebhookHandler.captured.clear()
    server = HTTPServer(("127.0.0.1", 0), _GenericWebhookHandler)
    _host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/hooks/slack-style"
    finally:
        server.shutdown()


@pytest.fixture()
def feishu_hook_url() -> str:
    _HookCaptureHandler.captured.clear()
    server = HTTPServer(("127.0.0.1", 0), _HookCaptureHandler)
    _host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{port}/open.feishu.cn/open-apis/bot/v2/hook/integration-test"
    finally:
        server.shutdown()


def _build_job(target: str) -> CronJob:
    return CronJob(
        id="job-integration-feishu",
        user_id="user-integration",
        name="daily-brief",
        job_type=JobType.AGENT,
        prompt="brief",
        schedule=Schedule(kind="cron", expr="0 9 * * *"),
        delivery=DeliveryConfig(channel="webhook", target=target),
    )


@pytest.mark.asyncio
async def test_deliver_feishu_bot_webhook_hits_real_http_server(feishu_hook_url: str) -> None:
    job = _build_job(feishu_hook_url)
    result = JobResult(success=True, output="Integration delivery body")

    await deliver_feishu_bot_webhook(job, result)

    payload = _HookCaptureHandler.captured["json"]
    assert isinstance(payload, dict)
    assert payload["msg_type"] == "text"
    assert "Integration delivery body" in payload["content"]["text"]
    assert "[daily-brief]" in payload["content"]["text"]


@pytest.mark.asyncio
async def test_channel_delivery_routes_feishu_hook_without_mock(feishu_hook_url: str) -> None:
    delivery_cfg = resolve_cron_delivery(feishu_hook_url)
    assert delivery_cfg.channel == "webhook"

    job = _build_job(delivery_cfg.target or feishu_hook_url)
    job.delivery = delivery_cfg

    await ChannelResultDelivery().deliver(job, JobResult(success=True, output="Channel route ok"))

    payload = _HookCaptureHandler.captured["json"]
    assert payload["msg_type"] == "text"
    assert "Channel route ok" in payload["content"]["text"]


def test_is_feishu_bot_hook_url_larksuite() -> None:
    assert is_feishu_bot_hook_url("https://open.larksuite.com/open-apis/bot/v2/hook/x")


def test_resolve_cron_delivery_empty_webhook_is_chat() -> None:
    cfg = resolve_cron_delivery("   ")
    assert cfg.channel == "chat"


@pytest.mark.asyncio
async def test_channel_delivery_generic_webhook_myrm_schema(generic_webhook_url: str) -> None:
    job = CronJob(
        id="job-generic-webhook",
        user_id="user-1",
        name="report",
        job_type=JobType.AGENT,
        prompt="run",
        schedule=Schedule(kind="cron", expr="0 8 * * *"),
        delivery=DeliveryConfig(channel="webhook", target=generic_webhook_url, secret="sign-key"),
    )

    await ChannelResultDelivery().deliver(
        job,
        JobResult(success=True, output="Generic webhook payload", metadata={"model": "test-model"}),
    )

    payload = _GenericWebhookHandler.captured["json"]
    headers = _GenericWebhookHandler.captured["headers"]
    assert payload["event"] == "cron.run.completed"
    assert payload["job_id"] == "job-generic-webhook"
    assert payload["status"] == "success"
    assert payload["output"] == "Generic webhook payload"
    assert "X-Webhook-Signature" in headers
    assert str(headers["X-Webhook-Signature"]).startswith("sha256=")


@pytest.mark.asyncio
async def test_channel_delivery_feishu_channel_legacy_path(feishu_hook_url: str) -> None:
    job = _build_job(feishu_hook_url)
    job.delivery = DeliveryConfig(channel="feishu", target=feishu_hook_url)

    await ChannelResultDelivery().deliver(job, JobResult(success=True, output="Legacy feishu channel"))

    payload = _HookCaptureHandler.captured["json"]
    assert payload["msg_type"] == "text"
    assert "Legacy feishu channel" in payload["content"]["text"]


@pytest.mark.asyncio
async def test_channel_delivery_silent_skips_http() -> None:
    _HookCaptureHandler.captured.clear()
    job = _build_job("https://example.com/ignored")
    job.delivery = DeliveryConfig(channel="silent", target="https://example.com/ignored")

    await ChannelResultDelivery().deliver(job, JobResult(success=True, output="silent"))

    assert _HookCaptureHandler.captured == {}


@pytest.mark.asyncio
async def test_feishu_delivery_includes_error_suffix(feishu_hook_url: str) -> None:
    job = _build_job(feishu_hook_url)
    await deliver_feishu_bot_webhook(
        job,
        JobResult(success=False, output="", error="upstream model timeout"),
    )
    text = _HookCaptureHandler.captured["json"]["content"]["text"]
    assert "upstream model timeout" in text


@pytest.mark.asyncio
async def test_feishu_delivery_empty_target_raises() -> None:
    job = _build_job("")
    with pytest.raises(ValueError, match="webhook URL missing"):
        await deliver_feishu_bot_webhook(job, JobResult(success=True, output="x"))


@pytest.mark.asyncio
async def test_deliver_feishu_bot_webhook_surfaces_api_error_code(feishu_hook_url: str) -> None:
    class _ErrorHandler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            length = int(self.headers.get("Content-Length", 0))
            if length:
                self.rfile.read(length)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"code":9499,"msg":"bad request"}')

        def log_message(self, format: str, *args: object) -> None:
            return

    server = HTTPServer(("127.0.0.1", 0), _ErrorHandler)
    host, port = server.server_address
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    error_url = f"http://127.0.0.1:{port}/open.feishu.cn/open-apis/bot/v2/hook/error"
    try:
        job = _build_job(error_url)
        with (
            patch("app.core.cron.adapters.feishu_bot_webhook._MAX_RETRIES", 0),
            pytest.raises(RuntimeError, match="9499"),
        ):
            await deliver_feishu_bot_webhook(job, JobResult(success=False, output="fail"))
    finally:
        server.shutdown()
