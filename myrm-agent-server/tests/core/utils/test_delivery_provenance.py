"""Unit tests for app.core.utils.delivery_provenance."""

from __future__ import annotations

from typing import cast

from app.core.utils.delivery_provenance import (
    apply_delivery_banner,
    apply_general_agent_pipeline_banner,
    ingress_from_channel_metadata,
    prepend_plain_banner,
    resolve_general_agent_pipeline_labels,
)


def test_ingress_from_channel_metadata_default() -> None:
    assert ingress_from_channel_metadata(None) == "local_connector"
    assert ingress_from_channel_metadata({}) == "local_connector"


def test_ingress_from_channel_metadata_control_plane() -> None:
    meta = cast(dict[str, object], {"trusted_inbound": "control_plane"})
    assert ingress_from_channel_metadata(meta) == "control_plane"


def test_prepend_plain_banner_shape() -> None:
    out = prepend_plain_banner(channel_label="slack", ingress_label="local_connector", body="hi")
    assert "[Inbound channel message] channel=slack ingress=local_connector" in out
    assert out.endswith("\nhi")


# Contract table: intentional branch coverage for prod ingress stability.
_PIPELINE_LABEL_CONTRACT: dict[str, tuple[str, str]] = {
    "web_chat": ("http_gui", "browser_sse"),
    "cron": ("cron", "cron_scheduler"),
    "eval": ("eval", "eval_runner"),
    "headless_wakeup": ("headless_wakeup", "async_wake_consumer"),
    "slack": ("slack", "server_pipeline"),
    "": ("http_gui", "browser_sse"),
}


def test_resolve_general_agent_pipeline_contract_table() -> None:
    """Guards deliberate resolver branches; fallback path covered separately."""
    for channel_name, expected in _PIPELINE_LABEL_CONTRACT.items():
        assert resolve_general_agent_pipeline_labels(channel_name) == expected


def test_resolve_general_agent_pipeline_unknown_uses_fallback_ingress() -> None:
    assert resolve_general_agent_pipeline_labels("custom_channel_xyz") == (
        "custom_channel_xyz",
        "server_pipeline",
    )


def test_apply_general_agent_pipeline_banner_matches_cron() -> None:
    out = cast(str, apply_general_agent_pipeline_banner("hi", channel_name="cron"))
    assert "channel=cron" in out
    assert "ingress=cron_scheduler" in out


def test_apply_delivery_http_gui_alias_str_idempotent() -> None:
    first = cast(str, apply_delivery_banner("hello", channel_label="http_gui", ingress_label="browser_sse"))
    second = cast(str, apply_delivery_banner(first, channel_label="http_gui", ingress_label="browser_sse"))
    assert first == second
    assert "http_gui" in first
    assert "browser_sse" in first


def test_apply_delivery_banner_multimodal_text_first_block() -> None:
    payload: list[object] = [{"type": "text", "text": "body"}]
    out = cast(list[object], apply_delivery_banner(payload, channel_label="http_gui", ingress_label="browser_sse"))
    text0 = out[0]
    assert isinstance(text0, dict)
    assert isinstance(text0.get("text"), str)
    assert "[Inbound channel message]" in cast(str, text0.get("text"))
