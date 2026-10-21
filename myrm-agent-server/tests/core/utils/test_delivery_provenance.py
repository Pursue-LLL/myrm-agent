"""Unit tests for app.core.utils.delivery_provenance."""

from __future__ import annotations

from typing import cast

from myrm_agent_harness.agent.skill_agent.skill_reference import parse_use_tag

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


# --- explicit skill invocation: the harness only recognizes ``[use skill]`` at the very start of the text ---

_WIRE = "[use hookprobe-1a2b3c4d] Run exactly this command: echo HOOK-E2E-OK"


def test_web_chat_banner_keeps_the_skill_invocation_recognizable() -> None:
    """The text a browser turn hands to SkillAgent.run must still parse as the user's explicit invocation."""
    received = cast(str, apply_general_agent_pipeline_banner(_WIRE, channel_name="web_chat"))

    invocation = parse_use_tag(received)
    assert invocation is not None
    assert invocation.references == ("hookprobe-1a2b3c4d",)
    assert invocation.text.startswith("[Inbound channel message] channel=http_gui ingress=browser_sse")
    assert invocation.text.endswith("Run exactly this command: echo HOOK-E2E-OK")


def test_banner_goes_first_when_there_is_no_skill_invocation() -> None:
    out = cast(str, apply_delivery_banner("plain words", channel_label="http_gui", ingress_label="browser_sse"))
    assert out.startswith("[Inbound channel message] channel=http_gui ingress=browser_sse")
    assert out.endswith("\n\nplain words")


def test_skill_invocation_banner_is_idempotent() -> None:
    first = cast(str, apply_delivery_banner(_WIRE, channel_label="http_gui", ingress_label="browser_sse"))
    second = cast(str, apply_delivery_banner(first, channel_label="http_gui", ingress_label="browser_sse"))
    assert first == second
    assert first.count("[Inbound channel message]") == 1


def test_prepend_plain_banner_keeps_the_skill_invocation_first() -> None:
    out = prepend_plain_banner(channel_label="slack", ingress_label="local_connector", body="[use a,b] go")
    assert out.startswith("[use a,b]\n\n[Inbound channel message] channel=slack")
    assert out.endswith("\n\ngo")


def test_skill_invocation_without_words_still_gets_a_banner() -> None:
    out = cast(str, apply_delivery_banner("[use a]", channel_label="http_gui", ingress_label="browser_sse"))
    invocation = parse_use_tag(out)
    assert invocation is not None and invocation.references == ("a",)
    assert "[Inbound channel message]" in invocation.text


def test_multimodal_first_text_block_keeps_the_skill_invocation_first() -> None:
    payload: list[object] = [{"type": "text", "text": "[use a] look at this"}, {"type": "image_url", "image_url": {}}]
    out = cast(list[object], apply_delivery_banner(payload, channel_label="http_gui", ingress_label="browser_sse"))

    first = cast(dict[str, object], out[0])
    invocation = parse_use_tag(cast(str, first["text"]))
    assert invocation is not None and invocation.references == ("a",)
    assert invocation.text.endswith("look at this")
    assert out[1] == payload[1]
