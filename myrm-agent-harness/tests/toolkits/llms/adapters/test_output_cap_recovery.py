"""Output-cap recovery of TransportChatModel: provider-stated ``max_tokens`` limits.

Real provider wordings go through the real error classifier and the real retry loops of all four
entry points (sync/async x non-stream/stream). Only the provider client is faked, with the response and chunk
shapes the transport returns. The recovery contract under test:

- a rejected request is retried with the limit the provider printed, and nothing else changes
  (so the provider-side prompt-prefix cache still hits);
- a model ceiling is remembered per endpoint, a window remainder is not;
- nothing is retried once the consumer has already received streamed output.

The wordings of individual providers (SiliconFlow, Cohere, TGI) are in test_output_cap_provider_wordings.py.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.toolkits.llms.adapters.chat_model import output_cap_recovery
from myrm_agent_harness.toolkits.llms.adapters.chat_model.output_cap_recovery import (
    apply_learned_output_cap,
    recover_output_cap,
)
from myrm_agent_harness.toolkits.llms.ephemeral_output_tokens import (
    get_ephemeral_max_output_tokens,
    set_ephemeral_max_output_tokens,
)
from myrm_agent_harness.toolkits.llms.transport import LLMHTTPError
from tests.support.output_cap_harness import (
    ASYNC_PATHS,
    CEILING,
    CEILING_ERROR,
    MESSAGES,
    MODEL,
    REQUESTED,
    SYNC_PATHS,
    WINDOW_ERROR,
    WINDOW_ERROR_NO_ROOM,
    WINDOW_REMAINDER_RETRY,
    assert_only_max_tokens_differs,
    async_stream,
    bad_request,
    build_model,
    max_tokens_sent,
    rate_limited,
    run_async,
    run_sync,
    script,
    sync_stream,
)

pytestmark = pytest.mark.usefixtures("isolated_ceiling_memo")


class TestRetryLoops:
    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_model_ceiling_is_retried_with_only_max_tokens_lowered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(CEILING_ERROR), "ok")

        assert run_sync(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, CEILING]
        assert_only_max_tokens_differs(client)

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_model_ceiling_is_retried_with_only_max_tokens_lowered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(CEILING_ERROR), "ok")

        assert await run_async(model, path) == "ok"

        assert max_tokens_sent(client) == [REQUESTED, CEILING]
        assert_only_max_tokens_differs(client)

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_next_request_starts_at_the_learned_ceiling(self, path: str) -> None:
        first = build_model()
        script(first, path, bad_request(CEILING_ERROR), "ok")
        run_sync(first, path)

        later = build_model()
        client = script(later, path, "ok")
        assert run_sync(later, path) == "ok"

        assert max_tokens_sent(client) == [CEILING]

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_next_request_starts_at_the_learned_ceiling(self, path: str) -> None:
        first = build_model()
        script(first, path, bad_request(CEILING_ERROR), "ok")
        await run_async(first, path)

        later = build_model()
        client = script(later, path, "ok")
        assert await run_async(later, path) == "ok"

        assert max_tokens_sent(client) == [CEILING]

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_window_remainder_keeps_a_margin_and_is_not_remembered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(WINDOW_ERROR), "ok")
        assert run_sync(model, path) == "ok"
        assert max_tokens_sent(client) == [REQUESTED, WINDOW_REMAINDER_RETRY]

        # The remainder belongs to that one request; a shorter prompt later gets the full budget again.
        later = build_model()
        client = script(later, path, "ok")
        run_sync(later, path)
        assert max_tokens_sent(client) == [REQUESTED]

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_window_remainder_keeps_a_margin_and_is_not_remembered(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(WINDOW_ERROR), "ok")
        assert await run_async(model, path) == "ok"
        assert max_tokens_sent(client) == [REQUESTED, WINDOW_REMAINDER_RETRY]

        later = build_model()
        client = script(later, path, "ok")
        await run_async(later, path)
        assert max_tokens_sent(client) == [REQUESTED]

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_remainder_too_small_to_answer_fails_fast_for_compression(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(WINDOW_ERROR_NO_ROOM), "ok")

        with pytest.raises(LLMHTTPError):
            run_sync(model, path)

        assert client.call_count == 1

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_remainder_too_small_to_answer_fails_fast_for_compression(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(WINDOW_ERROR_NO_ROOM), "ok")

        with pytest.raises(LLMHTTPError):
            await run_async(model, path)

        assert client.call_count == 1

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_sync_ceiling_that_would_not_lower_the_request_is_not_retried(self, path: str) -> None:
        model = build_model()
        client = script(model, path, bad_request(f"Range of max_tokens should be [1, {REQUESTED * 2}]"), "ok")

        with pytest.raises(LLMHTTPError):
            run_sync(model, path)

        assert client.call_count == 1

    @pytest.mark.parametrize("path", ASYNC_PATHS)
    async def test_async_rate_limit_with_similar_wording_is_not_retried(self, path: str) -> None:
        model = build_model()
        client = script(model, path, rate_limited(CEILING_ERROR), "ok")

        with pytest.raises(LLMHTTPError):
            await run_async(model, path)

        assert client.call_count == 1

    @pytest.mark.parametrize("path", SYNC_PATHS)
    def test_learned_ceiling_applies_after_the_truncation_boost_override(self, path: str) -> None:
        first = build_model()
        script(first, path, bad_request(CEILING_ERROR), "ok")
        run_sync(first, path)

        later = build_model()
        client = script(later, path, "ok")
        set_ephemeral_max_output_tokens(REQUESTED * 2)
        run_sync(later, path)

        assert max_tokens_sent(client) == [CEILING]
        assert get_ephemeral_max_output_tokens() is None


class TestNothingIsRetriedOnceStreamingStarted:
    """A retry restarts the stream; after the consumer received output it would duplicate that output."""

    MID_STREAM_ERRORS = (
        pytest.param(bad_request(CEILING_ERROR), id="model-ceiling"),
        pytest.param(bad_request(WINDOW_ERROR), id="window-remainder"),
        pytest.param(Exception("Unsupported parameter: 'stream_options'"), id="gateway-param"),
    )

    @pytest.mark.parametrize("error", MID_STREAM_ERRORS)
    def test_sync_error_after_streamed_output_propagates_without_a_restart(self, error: Exception) -> None:
        model = build_model()
        client = script(model, "stream", sync_stream(fail_with=error, after=1), "ok")
        received: list[str] = []

        with pytest.raises(type(error)):
            for chunk in model._stream(MESSAGES):
                received.append(str(chunk.message.content))

        assert received == ["Hello"]
        assert client.call_count == 1

    @pytest.mark.parametrize("error", MID_STREAM_ERRORS)
    async def test_async_error_after_streamed_output_propagates_without_a_restart(self, error: Exception) -> None:
        model = build_model()
        client = script(model, "astream", async_stream(fail_with=error, after=1), "ok")
        received: list[str] = []

        with pytest.raises(type(error)):
            async for chunk in model._astream(MESSAGES):
                received.append(str(chunk.message.content))

        assert received == ["Hello"]
        assert client.call_count == 1

    def test_sync_error_before_the_first_chunk_is_still_recovered(self) -> None:
        model = build_model()
        client = script(model, "stream", sync_stream(fail_with=bad_request(CEILING_ERROR)), "ok")

        assert run_sync(model, "stream") == "ok"
        assert max_tokens_sent(client) == [REQUESTED, CEILING]

    async def test_async_error_before_the_first_chunk_is_still_recovered(self) -> None:
        model = build_model()
        client = script(model, "astream", async_stream(fail_with=bad_request(CEILING_ERROR)), "ok")

        assert await run_async(model, "astream") == "ok"
        assert max_tokens_sent(client) == [REQUESTED, CEILING]


class TestRecoverOutputCap:
    def test_model_ceiling_is_adopted_as_stated_and_remembered(self) -> None:
        params: dict[str, object] = {"max_tokens": REQUESTED}

        assert recover_output_cap(bad_request(CEILING_ERROR), params, model=MODEL, base_url="")

        assert params["max_tokens"] == CEILING
        later: dict[str, object] = {"max_tokens": REQUESTED}
        apply_learned_output_cap(later, model=MODEL, base_url="")
        assert later["max_tokens"] == CEILING

    def test_unset_max_tokens_adopts_the_stated_ceiling(self) -> None:
        params: dict[str, object] = {}

        assert recover_output_cap(bad_request(CEILING_ERROR), params, model=MODEL, base_url="")

        assert params["max_tokens"] == CEILING

    @pytest.mark.parametrize("status_error", (rate_limited(CEILING_ERROR),), ids=("429",))
    def test_statuses_that_never_carry_an_output_limit_are_refused(self, status_error: Exception) -> None:
        params: dict[str, object] = {"max_tokens": REQUESTED}

        assert not recover_output_cap(status_error, params, model=MODEL, base_url="")

        assert params["max_tokens"] == REQUESTED

    def test_error_without_a_status_is_still_read(self) -> None:
        params: dict[str, object] = {"max_tokens": REQUESTED}

        assert recover_output_cap(Exception(CEILING_ERROR), params, model=MODEL, base_url="")

        assert params["max_tokens"] == CEILING

    def test_unrecognised_error_leaves_the_request_untouched(self) -> None:
        params: dict[str, object] = {"max_tokens": REQUESTED}

        assert not recover_output_cap(bad_request("messages: roles must alternate"), params, model=MODEL, base_url="")

        assert params == {"max_tokens": REQUESTED}

    @pytest.mark.parametrize(
        "params",
        (
            pytest.param(
                {"max_tokens": REQUESTED, "thinking": {"type": "enabled", "budget_tokens": CEILING}}, id="top-level"
            ),
            pytest.param(
                {
                    "max_tokens": REQUESTED,
                    "extra_body": {"thinking": {"type": "enabled", "budget_tokens": CEILING + 1}},
                },
                id="extra-body",
            ),
        ),
    )
    def test_ceiling_without_room_for_the_thinking_budget_is_refused(self, params: dict[str, object]) -> None:
        before = dict(params)

        assert not recover_output_cap(bad_request(CEILING_ERROR), params, model=MODEL, base_url="")

        assert params == before
        assert not output_cap_recovery._LEARNED_CEILINGS

    def test_ceiling_with_room_for_the_thinking_budget_is_adopted(self) -> None:
        params: dict[str, object] = {
            "max_tokens": REQUESTED,
            "thinking": {"type": "enabled", "budget_tokens": CEILING // 2},
        }

        assert recover_output_cap(bad_request(CEILING_ERROR), params, model=MODEL, base_url="")

        assert params["max_tokens"] == CEILING

    def test_memo_is_bounded_and_evicts_the_oldest_endpoint_first(self) -> None:
        limit = output_cap_recovery._LEARNED_CEILINGS_MAX
        for index in range(limit + 44):
            recover_output_cap(
                bad_request(CEILING_ERROR), {"max_tokens": REQUESTED}, model=f"{MODEL}-{index}", base_url=""
            )

        assert len(output_cap_recovery._LEARNED_CEILINGS) == limit
        assert (f"{MODEL}-0", "") not in output_cap_recovery._LEARNED_CEILINGS
        assert (f"{MODEL}-{limit + 43}", "") in output_cap_recovery._LEARNED_CEILINGS


class TestApplyLearnedOutputCap:
    @staticmethod
    def _learn(*, model: str = MODEL, base_url: str = "", expires_in: float = 60.0) -> None:
        output_cap_recovery._LEARNED_CEILINGS[(model.lower(), base_url.lower())] = (
            CEILING,
            time.monotonic() + expires_in,
        )

    def test_lowers_a_request_above_the_ceiling(self) -> None:
        self._learn()
        params: dict[str, object] = {"max_tokens": REQUESTED}

        apply_learned_output_cap(params, model=MODEL, base_url="")

        assert params["max_tokens"] == CEILING

    def test_never_raises_or_invents_a_budget(self) -> None:
        self._learn()
        lower: dict[str, object] = {"max_tokens": CEILING // 2}
        unset: dict[str, object] = {}

        apply_learned_output_cap(lower, model=MODEL, base_url="")
        apply_learned_output_cap(unset, model=MODEL, base_url="")

        assert lower == {"max_tokens": CEILING // 2}
        assert unset == {}

    def test_other_endpoints_are_untouched(self) -> None:
        self._learn(base_url="https://gateway-a.example/v1")
        params: dict[str, object] = {"max_tokens": REQUESTED}

        apply_learned_output_cap(params, model=MODEL, base_url="https://gateway-b.example/v1")

        assert params["max_tokens"] == REQUESTED

    def test_endpoint_key_ignores_case(self) -> None:
        self._learn(model=MODEL.upper(), base_url="HTTPS://Gateway.example/v1")
        params: dict[str, object] = {"max_tokens": REQUESTED}

        apply_learned_output_cap(params, model=MODEL, base_url="https://gateway.example/v1")

        assert params["max_tokens"] == CEILING

    def test_expired_ceiling_is_dropped_so_a_raised_provider_limit_is_picked_up(self) -> None:
        self._learn(expires_in=-1.0)
        params: dict[str, object] = {"max_tokens": REQUESTED}

        apply_learned_output_cap(params, model=MODEL, base_url="")

        assert params["max_tokens"] == REQUESTED
        assert not output_cap_recovery._LEARNED_CEILINGS
