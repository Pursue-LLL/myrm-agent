"""Wire-level proof of what a gateway receives for the reasoning controls.

Models of other families (DeepSeek, Qwen) reach their gateway through the ``openai/`` route segment. Each test builds
the LLM through the production factory, makes real calls against a loopback gateway and inspects the request bodies
that arrived there: a rule that is right on the Python side but altered on the way out is invisible to unit tests.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import pytest
from langchain_core.messages import HumanMessage

from myrm_agent_harness.toolkits.llms.adapters import gateway_normalizer
from myrm_agent_harness.toolkits.llms.core.llm import create_chat_model
from tests.mocks.llm_wire_server import FakeProviderServer, FakeReply, JsonBody, openai_text_stream

DEEPSEEK_ON_GATEWAY = "openai/deepseek-v4.1-flash"
QWEN_ON_GATEWAY = "openai/Qwen/Qwen3-32B"


@pytest.fixture(autouse=True)
def _isolated_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    monkeypatch.setattr(gateway_normalizer, "_REJECTED_REASONING", {})


def _accepting(body: JsonBody) -> FakeReply:
    """A finished answer, streamed or whole as the request asked."""
    if body.get("stream"):
        return FakeReply(openai_text_stream())
    completion = {
        "id": "chatcmpl-fake",
        "object": "chat.completion",
        "created": 1,
        "model": "fake",
        "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
    }
    return FakeReply(json.dumps(completion).encode(), content_type="application/json")


def _rejecting(*controls: str) -> Callable[[JsonBody], FakeReply]:
    """A gateway that answers 400 to the first of ``controls`` found in the body, as strict gateways do."""

    def respond(body: JsonBody) -> FakeReply:
        rejected = next((control for control in controls if control in body), None)
        if rejected is None:
            return _accepting(body)
        error = {
            "error": {"message": f"Unrecognized request argument supplied: {rejected}", "type": "invalid_request_error"}
        }
        return FakeReply(json.dumps(error).encode(), status=400, content_type="application/json")

    return respond


async def _bodies(
    model: str,
    respond: Callable[[JsonBody], FakeReply] = _accepting,
    *,
    calls: int = 1,
    streaming: bool = True,
    **kwargs: str,
) -> list[JsonBody]:
    """Make ``calls`` fresh-model calls through the production factory; return every body the gateway received."""
    with FakeProviderServer(respond) as server:
        for _ in range(calls):
            llm = create_chat_model(
                model, base_url=f"{server.base_url}/v1", api_key="sk-offline", streaming=streaming, **kwargs
            )
            await llm.ainvoke([HumanMessage(content="hello")])
    return server.requests


class TestExplicitControlsReachTheGateway:
    @pytest.mark.parametrize("level", ["low", "high", "max"])
    async def test_a_level_is_sent_as_the_effort_without_a_thinking_field(self, level: str) -> None:
        (body,) = await _bodies(DEEPSEEK_ON_GATEWAY, reasoning_effort=level)

        assert body["reasoning_effort"] == level
        assert "thinking" not in body

    async def test_off_is_sent_as_the_disable_switch_and_never_as_an_effort(self) -> None:
        (body,) = await _bodies(DEEPSEEK_ON_GATEWAY, reasoning_effort="off")

        assert body["thinking"] == {"type": "disabled"}
        assert "reasoning_effort" not in body

    async def test_unspecified_effort_sends_no_reasoning_control(self) -> None:
        (body,) = await _bodies(DEEPSEEK_ON_GATEWAY)

        assert "reasoning_effort" not in body
        assert "thinking" not in body

    async def test_an_effort_of_another_family_passes_through(self) -> None:
        (body,) = await _bodies(QWEN_ON_GATEWAY, reasoning_effort="high")

        assert body["reasoning_effort"] == "high"
        assert "thinking" not in body

    async def test_off_of_another_family_is_not_sent_as_an_effort(self) -> None:
        (body,) = await _bodies(QWEN_ON_GATEWAY, reasoning_effort="off")

        assert "reasoning_effort" not in body
        assert "thinking" not in body


class TestOffIsNeverSentAsALevel:
    """``off`` is the user's request to think less; no OpenAI-shaped provider has a level of that name."""

    @pytest.mark.parametrize(
        "model",
        [
            "openrouter/deepseek/deepseek-v4-pro",
            "groq/llama-3.3-70b-versatile",
            "mistral/mistral-large-latest",
            "moonshot/kimi-k2-0905-preview",
            "dashscope/qwen-plus",
        ],
    )
    async def test_an_untranslatable_off_is_omitted(self, model: str) -> None:
        (body,) = await _bodies(model, reasoning_effort="off")

        assert "reasoning_effort" not in body
        assert "reasoning" not in body

    async def test_openrouter_still_nests_a_real_level(self) -> None:
        (body,) = await _bodies("openrouter/deepseek/deepseek-v4-pro", reasoning_effort="high")

        assert body["reasoning"] == {"effort": "high"}


class TestOpenAiModelsBehindTheSameSegmentKeepTheirRules:
    async def test_a_non_reasoning_openai_model_never_gets_an_effort(self) -> None:
        (body,) = await _bodies("openai/gpt-4o", reasoning_effort="low")

        assert "reasoning_effort" not in body

    async def test_an_openai_reasoning_model_is_remapped_to_a_level_it_accepts(self) -> None:
        (body,) = await _bodies("openai/gpt-5.6", reasoning_effort="max")

        assert body["reasoning_effort"] == "high"


@pytest.mark.parametrize("streaming", [True, False], ids=["stream", "no-stream"])
class TestGatewayThatRejectsAControl:
    async def test_effort_rejection_is_retried_without_the_effort(self, streaming: bool) -> None:
        sent = await _bodies(
            DEEPSEEK_ON_GATEWAY, _rejecting("reasoning_effort"), streaming=streaming, reasoning_effort="max"
        )

        assert [body.get("reasoning_effort") for body in sent] == ["max", None]

    async def test_thinking_rejection_is_retried_without_the_switch(self, streaming: bool) -> None:
        sent = await _bodies(DEEPSEEK_ON_GATEWAY, _rejecting("thinking"), streaming=streaming, reasoning_effort="off")

        assert ["thinking" in body for body in sent] == [True, False]

    async def test_the_rejection_is_remembered_by_the_next_call(self, streaming: bool) -> None:
        sent = await _bodies(
            DEEPSEEK_ON_GATEWAY,
            _rejecting("reasoning_effort"),
            calls=2,
            streaming=streaming,
            reasoning_effort="max",
        )

        assert [body.get("reasoning_effort") for body in sent] == ["max", None, None]
