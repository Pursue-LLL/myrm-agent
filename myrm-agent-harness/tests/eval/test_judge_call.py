"""judge_completion: request shape, answer extraction and bounded retry of transient failures."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest

from myrm_agent_harness.eval.judge_call import judge_completion
from myrm_agent_harness.toolkits.llms.transport.errors import LLMHTTPError


def _completion(text: str) -> dict[str, object]:
    return {"choices": [{"message": {"role": "assistant", "content": text}}]}


def _http_error(status: int) -> LLMHTTPError:
    request = httpx.Request("POST", "https://api.example.com/v1/chat/completions")
    response = httpx.Response(status, json={"error": {"message": "x"}}, request=request)
    return LLMHTTPError("openai", status, response.text, response)


@pytest.fixture
def transport():
    mock = AsyncMock()
    with (
        patch("myrm_agent_harness.toolkits.llms.text_completion.get_transport", return_value=mock),
        patch("asyncio.sleep", new_callable=AsyncMock),
    ):
        yield mock.acompletion


async def test_request_shape_and_answer_extraction(transport: AsyncMock) -> None:
    transport.return_value = _completion("  PASS \n")

    answer = await judge_completion(
        model="deepseek/deepseek-chat", prompt="judge this", api_key="k", api_base="https://b"
    )

    assert answer == "PASS"
    transport.assert_awaited_once_with(
        model="deepseek/deepseek-chat",
        messages=[{"role": "user", "content": "judge this"}],
        temperature=0.0,
        api_key="k",
        api_base="https://b",
    )


async def test_credentials_are_omitted_when_unset(transport: AsyncMock) -> None:
    transport.return_value = _completion("PASS")
    await judge_completion(model="gpt-4o-mini", prompt="p")
    assert set(transport.await_args.kwargs) == {"model", "messages", "temperature"}


@pytest.mark.parametrize("failure", [_http_error(429), _http_error(503), httpx.ConnectError("refused")])
async def test_transient_failures_are_retried(transport: AsyncMock, failure: Exception) -> None:
    transport.side_effect = [failure, failure, _completion("PASS")]
    assert await judge_completion(model="m", prompt="p") == "PASS"
    assert transport.await_count == 3


async def test_retries_are_bounded(transport: AsyncMock) -> None:
    transport.side_effect = _http_error(503)
    with pytest.raises(LLMHTTPError):
        await judge_completion(model="m", prompt="p")
    assert transport.await_count == 3


@pytest.mark.parametrize("status", [400, 401, 404])
async def test_permanent_failures_surface_at_once(transport: AsyncMock, status: int) -> None:
    transport.side_effect = _http_error(status)
    with pytest.raises(LLMHTTPError):
        await judge_completion(model="m", prompt="p")
    assert transport.await_count == 1


async def test_a_model_without_an_answer_yields_empty_text(transport: AsyncMock) -> None:
    transport.return_value = {"choices": []}
    assert await judge_completion(model="m", prompt="p") == ""
