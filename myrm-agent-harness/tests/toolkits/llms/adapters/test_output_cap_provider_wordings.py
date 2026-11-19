"""Output-cap recovery for the flat-body wordings of SiliconFlow, Cohere and Hugging Face TGI.

Each provider's recorded sentence goes through the real error classifier and the real retry loops of all four
entry points; the budget the sentence states must reach the retry, and a neighbouring prompt-overflow sentence
must not be read as an output limit.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport import LLMHTTPError
from tests.support.output_cap_harness import (
    ASYNC_PATHS,
    CEILING,
    REQUESTED,
    SYNC_PATHS,
    assert_only_max_tokens_differs,
    build_model,
    max_tokens_sent,
    run_async,
    run_sync,
    script,
)
from tests.support.provider_errors import provider_error

pytestmark = pytest.mark.usefixtures("isolated_ceiling_memo")


# SiliconFlow's own wording of a model ceiling, and the sentence form other gateways and clients print.
SILICONFLOW_WORDINGS = (
    f"max_tokens: Must be less than or equal to {CEILING}",
    f"max_tokens must be less than or equal to {CEILING}.",
)


class TestSiliconFlowFlatBody:
    """SiliconFlow answers with a flat ``{code, message, data}`` body instead of an ``error`` envelope."""

    @staticmethod
    def _rejection(message: str) -> Exception:
        return provider_error("openai", 400, {"code": 20015, "message": message, "data": None})

    @pytest.mark.parametrize("message", SILICONFLOW_WORDINGS)
    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_max_tokens_ceiling_is_retried(self, path: str, message: str) -> None:
        model = build_model()
        client = script(model, path, self._rejection(message), "ok")

        assert run_sync(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, CEILING]
        assert_only_max_tokens_differs(client)

    @pytest.mark.parametrize("message", SILICONFLOW_WORDINGS)
    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_max_tokens_ceiling_is_retried(self, path: str, message: str) -> None:
        model = build_model()
        client = script(model, path, self._rejection(message), "ok")

        assert await run_async(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, CEILING]
        assert_only_max_tokens_differs(client)


# Cohere's wording of a model ceiling (400) and Hugging Face TGI's wording of a window total (422): 3000 prompt
# tokens leave 1096 of a 4096 window.
COHERE_ERROR = (
    f"too many tokens: max tokens must be less than or equal to {CEILING}, the maximum output length for this model "
    f"- received {REQUESTED}."
)
TGI_ERROR = (
    "Input validation error: `inputs` tokens + `max_new_tokens` must be <= 4096. "
    "Given: 3000 `inputs` tokens and 2000 `max_new_tokens`"
)
TGI_ERROR_PROMPT_OVERFLOW = TGI_ERROR.replace("3000", "5000")
TGI_REMAINDER_RETRY = 4096 - 3000 - 64


class TestCohereAndTGIRejections:
    """Both providers answer with a flat body; the budget in their sentence must reach the retry."""

    @staticmethod
    def _cohere(message: str = COHERE_ERROR) -> Exception:
        return provider_error("cohere", 400, {"message": message})

    @staticmethod
    def _tgi(message: str = TGI_ERROR) -> Exception:
        return provider_error("openai", 422, {"error": message, "error_type": "validation"})

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_cohere_ceiling_is_retried_and_remembered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, self._cohere(), "ok")

        assert run_sync(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, CEILING]
        assert_only_max_tokens_differs(client)
        later = build_model()
        client = script(later, path, "ok")
        run_sync(later, path)
        assert max_tokens_sent(client) == [CEILING]

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_cohere_ceiling_is_retried_and_remembered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, self._cohere(), "ok")

        assert await run_async(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, CEILING]
        assert_only_max_tokens_differs(client)
        later = build_model()
        client = script(later, path, "ok")
        await run_async(later, path)
        assert max_tokens_sent(client) == [CEILING]

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_tgi_window_total_is_retried_with_a_margin_and_not_remembered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, self._tgi(), "ok")

        assert run_sync(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, TGI_REMAINDER_RETRY]
        assert_only_max_tokens_differs(client)
        later = build_model()
        client = script(later, path, "ok")
        run_sync(later, path)
        assert max_tokens_sent(client) == [REQUESTED]

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_tgi_window_total_is_retried_with_a_margin_and_not_remembered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, self._tgi(), "ok")

        assert await run_async(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, TGI_REMAINDER_RETRY]
        assert_only_max_tokens_differs(client)
        later = build_model()
        client = script(later, path, "ok")
        await run_async(later, path)
        assert max_tokens_sent(client) == [REQUESTED]

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_tgi_prompt_that_overflows_the_window_fails_fast_for_compression(self, path: str) -> None:
        model = build_model()
        client = script(model, path, self._tgi(TGI_ERROR_PROMPT_OVERFLOW), "ok")

        with pytest.raises(LLMHTTPError):
            run_sync(model, path)

        assert client.call_count == 1

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_cohere_prompt_overflow_is_not_read_as_an_output_limit(self, path: str) -> None:
        model = build_model()
        overflow = (
            "too many tokens: size limit exceeded by 168512 tokens. Try using shorter or fewer inputs. "
            "The limit for this model is 132000 tokens."
        )
        client = script(model, path, self._cohere(overflow), "ok")

        with pytest.raises(LLMHTTPError):
            await run_async(model, path)

        assert client.call_count == 1
