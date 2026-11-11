"""Signed reasoning between the wire and the conversation: captured into a message, handed back from it.

The transports return a block as the provider wrote it; the adapter keeps it on the AIMessage in ``additional_kwargs``
and puts it back on the next request. A block the provider would refuse (unsigned, empty) never enters the message.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk
from langchain_core.outputs import ChatGenerationChunk

from myrm_agent_harness.core.thinking_blocks import THINKING_BLOCKS_KEY
from myrm_agent_harness.toolkits.llms.adapters.converters import convert_dict_to_message, convert_message_to_dict
from myrm_agent_harness.toolkits.llms.adapters.stream_aggregator import StreamAggregator, finalize_stream
from myrm_agent_harness.toolkits.llms.adapters.streaming import extract_replay_state

_SIGNED = {"type": "thinking", "thinking": "plan", "signature": "sig-1"}
_REDACTED = {"type": "redacted_thinking", "data": "opaque"}
_UNSIGNED = {"type": "thinking", "thinking": "no signature"}


def _answer(*blocks: dict[str, str]) -> AIMessage:
    return AIMessage(content="ok", additional_kwargs={THINKING_BLOCKS_KEY: list(blocks)})


class TestMessageConversion:
    @pytest.mark.parametrize("wire_protocol", [None, "chat_completions", "responses", "anthropic_messages"])
    def test_a_message_hands_its_blocks_back_whatever_the_adapter_protocol(self, wire_protocol: str | None) -> None:
        sent = convert_message_to_dict(_answer(_SIGNED, _UNSIGNED, _REDACTED), wire_protocol=wire_protocol)

        assert sent[THINKING_BLOCKS_KEY] == [_SIGNED, _REDACTED]

    def test_the_request_gets_a_copy_so_the_conversation_keeps_its_own(self) -> None:
        message = _answer(_SIGNED)

        sent = convert_message_to_dict(message)
        sent[THINKING_BLOCKS_KEY][0]["signature"] = "tampered"

        assert message.additional_kwargs[THINKING_BLOCKS_KEY] == [_SIGNED]

    def test_a_message_without_blocks_sends_no_key(self) -> None:
        assert THINKING_BLOCKS_KEY not in convert_message_to_dict(AIMessage(content="ok"))
        assert THINKING_BLOCKS_KEY not in convert_message_to_dict(_answer(_UNSIGNED))

    def test_an_answer_keeps_the_blocks_the_provider_would_take_back(self) -> None:
        message = convert_dict_to_message(
            {"role": "assistant", "content": "ok", THINKING_BLOCKS_KEY: [_SIGNED, _UNSIGNED, _REDACTED]}
        )

        assert message.additional_kwargs[THINKING_BLOCKS_KEY] == [_SIGNED, _REDACTED]

    def test_an_answer_without_blocks_leaves_the_message_without_the_key(self) -> None:
        message = convert_dict_to_message({"role": "assistant", "content": "ok"})

        assert THINKING_BLOCKS_KEY not in message.additional_kwargs


class TestStreamState:
    def test_a_delta_hands_over_its_blocks_and_its_responses_items(self) -> None:
        state = extract_replay_state(
            {"responses_reasoning_items": [{"id": "rs_1"}], THINKING_BLOCKS_KEY: [_SIGNED, _UNSIGNED]}
        )

        assert state == {"responses_reasoning_items": [{"id": "rs_1"}], THINKING_BLOCKS_KEY: [_SIGNED]}

    def test_a_delta_without_reasoning_state_hands_over_nothing(self) -> None:
        assert (
            extract_replay_state({"content": "hi", THINKING_BLOCKS_KEY: [_UNSIGNED], "responses_reasoning_items": []})
            == {}
        )

    def test_the_aggregator_keeps_the_blocks_in_the_order_they_closed(self) -> None:
        agg = StreamAggregator(AIMessageChunk)
        for block in (_REDACTED, _SIGNED):
            chunk = AIMessageChunk(content="", additional_kwargs={THINKING_BLOCKS_KEY: [block]})
            agg.on_generation_chunk(ChatGenerationChunk(message=chunk), AIMessageChunk)

        assert agg.thinking_blocks == [_REDACTED, _SIGNED]

    def test_the_finished_stream_carries_all_blocks_on_exactly_one_chunk(self) -> None:
        agg = StreamAggregator(AIMessageChunk)
        agg.content = ["answer"]
        agg.finish_reason = "stop"
        agg.thinking_blocks = [_REDACTED, _SIGNED]

        with (
            patch(
                "myrm_agent_harness.toolkits.llms.adapters.stream_aggregator.build_final_tool_call_chunk",
                return_value=(None, [], []),
            ),
            patch("myrm_agent_harness.toolkits.llms.utils.logger.log_llm_response"),
            patch("myrm_agent_harness.utils.token_economics.tracker.record_finish_reason"),
        ):
            result = finalize_stream(agg, None, "claude", is_async=True, record_usage_fn=MagicMock())

        assert result.aggregated_response["choices"][0]["message"][THINKING_BLOCKS_KEY] == [_REDACTED, _SIGNED]
        assert result.final_tool_chunk is not None
        assert result.final_tool_chunk.message.additional_kwargs[THINKING_BLOCKS_KEY] == [_REDACTED, _SIGNED]
