"""The follow-up suggestion call: a fixed cost envelope (bounded model output and conversation input) and a trace of the replies it cannot use."""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Iterator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from myrm_agent_harness.agent.middlewares.security.outbound_privacy_guard import set_process_privacy_policy
from myrm_agent_harness.toolkits.llms.adapters.chat_model.outbound_guard import set_outbound_message_guard

from app.api.agents.suggestions import SuggestionsRequest, get_suggestions
from app.core.security.privacy_policy_sync import sync_privacy_policy
from app.core.types import ModelConfig
from tests.support.privacy_wire import wire_llm

_REPLY = ["Why Rust?", "Rust vs Go?", "Is Rust hard?"]
_PHONE = "13812345678"


@pytest.fixture(autouse=True)
def _clean_process_policy() -> Iterator[None]:
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)
    yield
    set_process_privacy_policy(None)
    set_outbound_message_guard(None)


async def _call(
    history: list[list[str]],
    *,
    reply: str,
    model: ModelConfig | None = None,
    personal_settings: dict[str, object] | None = None,
) -> tuple[list[str], ModelConfig, str]:
    """Run the endpoint; return its suggestions, the config the model was built from and the text that reached the provider."""
    settings = personal_settings or {"privacyEnabled": False}
    sync_privacy_policy(settings)
    llm, sent = wire_llm(reply)
    build_llm = AsyncMock(return_value=llm)
    configs = SimpleNamespace(providers_dict={"providers": []}, model_cfg=None, personal_settings_dict=settings)
    lite = model or ModelConfig(model="test-model", api_key="test-key")
    with (
        patch("app.core.channel_bridge.config_loader.load_user_configs", new=AsyncMock(return_value=configs)),
        patch("app.api.agents.suggestions._resolve_lite_model", new=lambda *_args: lite),
        patch("myrm_agent_harness.toolkits.llms.llm_manager.get_llm_from_config", new=build_llm),
    ):
        # Past the rate limiter: the endpoint itself is under test.
        response = await inspect.unwrap(get_suggestions)(
            request=SuggestionsRequest(chat_history=history),
            http_request=MagicMock(),
        )

    assert build_llm.await_args is not None
    return json.loads(response.body)["data"]["suggestions"], build_llm.await_args.args[0], "\n".join(sent)


async def _suggest(
    history: list[list[str]],
    *,
    model: ModelConfig | None = None,
    personal_settings: dict[str, object] | None = None,
) -> tuple[ModelConfig, str]:
    """Run the endpoint against a clean reply; return the config the model was built from and the text that reached the provider."""
    suggestions, built_from, wire = await _call(
        history, reply=json.dumps(_REPLY), model=model, personal_settings=personal_settings
    )
    assert suggestions == _REPLY
    return built_from, wire


@pytest.mark.asyncio
async def test_output_is_capped_and_never_lifted_to_a_thinking_models_floor() -> None:
    lite = ModelConfig(
        model="test-model",
        api_key="test-key",
        model_kwargs={"top_p": 0.9, "max_tokens": 64000, "supports_reasoning": True},
    )

    built_from, _ = await _suggest([["human", "Hi"], ["assistant", "Hello"]], model=lite)

    assert built_from.model_kwargs == {"top_p": 0.9, "max_tokens": 1024, "supports_reasoning": False}
    assert lite.model_kwargs == {"top_p": 0.9, "max_tokens": 64000, "supports_reasoning": True}


@pytest.mark.asyncio
async def test_a_model_without_extra_kwargs_gets_the_same_envelope() -> None:
    built_from, _ = await _suggest([["human", "Hi"], ["assistant", "Hello"]])

    assert built_from.model_kwargs == {"max_tokens": 1024, "supports_reasoning": False}


@pytest.mark.asyncio
async def test_only_the_last_six_messages_are_sent() -> None:
    history = [[role, f"{role} turn {number}"] for number in range(4) for role in ("human", "assistant")]

    _, wire = await _suggest(history)

    assert "human turn 0" not in wire
    assert "assistant turn 0" not in wire
    assert "human turn 1" in wire
    assert "assistant turn 3" in wire


@pytest.mark.asyncio
async def test_a_long_message_keeps_its_opening_and_its_ending() -> None:
    answer = "OPENING " + "a" * 2000 + " MIDDLE " + "b" * 2000 + " ENDING"

    _, wire = await _suggest([["human", "Hi"], ["assistant", answer]])

    assert "OPENING" in wire
    assert "ENDING" in wire
    assert "MIDDLE" not in wire
    assert len(wire) < 2000


@pytest.mark.asyncio
async def test_a_message_at_the_limit_is_sent_whole() -> None:
    answer = "x" * 1500

    _, wire = await _suggest([["human", "Hi"], ["assistant", answer]])

    assert answer in wire
    assert "…" not in wire


@pytest.mark.asyncio
async def test_a_number_straddling_the_cut_is_masked_before_the_cut() -> None:
    """Cut first, mask second would hand the provider half a number that no pattern recognizes."""
    answer = "x" * 990 + f"手机 {_PHONE}" + "y" * 2000

    _, wire = await _suggest(
        [["human", "Hi"], ["assistant", answer]],
        personal_settings={"privacyEnabled": True, "privacyS2Action": "redact"},
    )

    assert _PHONE not in wire
    assert _PHONE[:7] not in wire


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "reply",
    [
        pytest.param("I cannot help with that, but my secret marker is ZEBRA-4821.", id="prose"),
        pytest.param("", id="empty"),
    ],
)
async def test_a_reply_without_a_usable_label_is_logged_by_its_length_only(reply: str, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.api.agents.suggestions"):
        suggestions, _, _ = await _call([["human", "Hi"], ["assistant", "Hello"]], reply=reply)

    assert suggestions == []
    ours = [record.getMessage() for record in caplog.records if record.name == "app.api.agents.suggestions"]
    assert ours == [f"suggestions_reply_unusable reply_chars={len(reply)}"]


@pytest.mark.asyncio
async def test_a_clean_reply_leaves_no_trace(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING, logger="app.api.agents.suggestions"):
        await _suggest([["human", "Hi"], ["assistant", "Hello"]])

    assert [record for record in caplog.records if record.name == "app.api.agents.suggestions"] == []
