"""Tests for cron delivery resolver."""

from __future__ import annotations

from app.core.cron.adapters.delivery_resolver import resolve_cron_delivery


def test_resolve_cron_delivery_empty_is_chat() -> None:
    cfg = resolve_cron_delivery("")
    assert cfg.channel == "chat"
    assert cfg.secret is None


def test_resolve_cron_delivery_feishu_hook_is_webhook_channel() -> None:
    url = "https://open.feishu.cn/open-apis/bot/v2/hook/xxx"
    cfg = resolve_cron_delivery(url)
    assert cfg.channel == "webhook"
    assert cfg.target == url
    assert cfg.secret is not None
    assert len(cfg.secret) == 64


def test_resolve_cron_delivery_generic_webhook() -> None:
    url = "https://hooks.slack.com/services/xxx"
    cfg = resolve_cron_delivery(url)
    assert cfg.channel == "webhook"
    assert cfg.target == url
    assert cfg.secret is not None


def test_resolve_cron_delivery_generates_fresh_secret_each_call() -> None:
    url = "https://hooks.slack.com/services/xxx"
    assert resolve_cron_delivery(url).secret != resolve_cron_delivery(url).secret
