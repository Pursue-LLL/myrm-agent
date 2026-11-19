"""Shared fakes and constants for the tests of TransportChatModel's output-cap recovery.

[INPUT]
- adapters.chat_model::TransportChatModel (POS: the model whose retry loops are driven)
- tests.support.provider_errors::provider_error (POS: the exception the transport really raises)

[OUTPUT]
- constants: MODEL / REQUESTED / CEILING and the wordings of a model ceiling and a window remainder
- build_model / script / run_sync / run_async: a model on a faked provider client and the four entry points
- max_tokens_sent / assert_only_max_tokens_differs: what the retries sent to the provider

[POS]
Only the provider client is faked, with the response and chunk shapes the transport returns, so the tests
that use it exercise the real error classifier and the real sync/async x non-stream/stream retry loops.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from typing import cast
from unittest.mock import AsyncMock, MagicMock

from langchain_core.messages import BaseMessage, HumanMessage

from myrm_agent_harness.toolkits.llms.adapters.chat_model import TransportChatModel
from tests.support.provider_errors import provider_error

MODEL = "openai/capped-model"
REQUESTED = 16384
CEILING = 8192

# DashScope wording of a model ceiling.
CEILING_ERROR = f"Range of max_tokens should be [1, {CEILING}]"
# Anthropic wording of a window remainder: 198000 prompt tokens leave 2000 of a 200000 window.
WINDOW_ERROR = (
    "input length and max_tokens exceed context limit: 198000 + 16384 > 200000, "
    "decrease input length or max_tokens and try again"
)
WINDOW_ERROR_NO_ROOM = WINDOW_ERROR.replace("198000", "199800")
WINDOW_REMAINDER_RETRY = 2000 - 64

MESSAGES: list[BaseMessage] = [HumanMessage(content="hi")]
SYNC_PATHS = ("generate", "stream")
ASYNC_PATHS = ("agenerate", "astream")


def bad_request(message: str) -> Exception:
    return provider_error("openai", 400, {"error": {"message": message, "type": "invalid_request_error"}})


def rate_limited(message: str) -> Exception:
    return provider_error("openai", 429, {"error": {"message": message, "type": "rate_limit_error"}})


def build_model() -> TransportChatModel:
    model = TransportChatModel(model=MODEL, max_tokens=REQUESTED)
    model.client = MagicMock()
    return model


def delta(text: str, finish_reason: str | None = None) -> dict[str, object]:
    return {"choices": [{"index": 0, "delta": {"content": text, "role": "assistant"}, "finish_reason": finish_reason}]}


def sync_stream(*, fail_with: Exception | None = None, after: int = 0) -> Iterator[dict[str, object]]:
    """Yield ``after`` chunks of 'Hello', then raise ``fail_with`` or finish normally."""
    for _ in range(after):
        yield delta("Hello")
    if fail_with is not None:
        raise fail_with
    yield delta("ok", "stop")


async def async_stream(*, fail_with: Exception | None = None, after: int = 0) -> AsyncIterator[dict[str, object]]:
    for _ in range(after):
        yield delta("Hello")
    if fail_with is not None:
        raise fail_with
    yield delta("ok", "stop")


def success(path: str) -> object:
    if path in ("generate", "agenerate"):
        return {"choices": [{"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}]}
    return sync_stream() if path == "stream" else async_stream()


def script(model: TransportChatModel, path: str, *outcomes: object) -> MagicMock:
    """Install the provider fake for ``path``: exceptions are raised, the string 'ok' becomes a normal response."""
    resolved = [success(path) if outcome == "ok" else outcome for outcome in outcomes]
    client = cast("MagicMock", model.client)  # build_model() installed a MagicMock
    if path in ASYNC_PATHS:
        client.acompletion = AsyncMock(side_effect=resolved)
        return cast("MagicMock", client.acompletion)
    client.completion = MagicMock(side_effect=resolved)
    return cast("MagicMock", client.completion)


def run_sync(model: TransportChatModel, path: str) -> str:
    if path == "generate":
        return str(model._generate(MESSAGES).generations[0].message.content)
    return "".join(str(chunk.message.content) for chunk in model._stream(MESSAGES))


async def run_async(model: TransportChatModel, path: str) -> str:
    if path == "agenerate":
        return str((await model._agenerate(MESSAGES)).generations[0].message.content)
    return "".join([str(chunk.message.content) async for chunk in model._astream(MESSAGES)])


def max_tokens_sent(client: MagicMock) -> list[int]:
    return [call.kwargs["max_tokens"] for call in client.call_args_list]


def assert_only_max_tokens_differs(client: MagicMock) -> None:
    """The retry must keep messages, tools and thinking parameters identical so the provider's prompt cache hits."""
    first, second = (call.kwargs for call in client.call_args_list)
    assert {k: v for k, v in first.items() if k != "max_tokens"} == {
        k: v for k, v in second.items() if k != "max_tokens"
    }
