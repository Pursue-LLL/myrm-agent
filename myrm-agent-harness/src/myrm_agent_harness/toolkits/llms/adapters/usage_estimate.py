"""Token usage counted locally for a stream whose provider reported none.

[INPUT]
- utils.token_estimation::estimate_messages_tokens (POS: tokens of the prompt messages)
- utils.text_utils::get_token_count (POS: tokens of generated text)

[OUTPUT]
- estimate_stream_usage: a ``usage`` dict counted from what was sent and what came back

[POS]
Many compatible gateways stream without a usage chunk. Left alone, such a call would never reach the request-scoped
tracker, the budget checker or the ledger, so its tokens are counted from the prompt that was sent and the text,
reasoning and tool calls that came back. The estimate feeds accounting only: it is never written onto a message's
``usage_metadata``, which stays empty because the provider reported nothing.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from langchain_core.messages import BaseMessage

from myrm_agent_harness.utils.text_utils import get_token_count
from myrm_agent_harness.utils.token_estimation import estimate_messages_tokens

# OpenAI's own chat accounting counts the opening of the assistant's reply, which primes every prompt.
_REPLY_PRIMING_TOKENS = 3


def _as_written(call: Mapping[str, object]) -> str:
    """A tool call the way it travels in a chat answer, envelope included, since the model wrote all of it."""
    function = call.get("function")
    parts = function if isinstance(function, Mapping) else {}
    envelope = {
        "function": {"arguments": parts.get("arguments") or "", "name": parts.get("name") or ""},
        "id": call.get("id") or "",
        "type": "function",
    }
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":"))


def estimate_stream_usage(
    prompt_messages: Sequence[BaseMessage], *, text: str, tool_calls: Sequence[Mapping[str, object]]
) -> dict[str, int]:
    """``usage`` of a finished stream: the prompt's tokens, and those of ``text`` plus every tool call written."""
    prompt_tokens = estimate_messages_tokens(list(prompt_messages)) + _REPLY_PRIMING_TOKENS
    completion_tokens = get_token_count("".join([text, *map(_as_written, tool_calls)]))
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": prompt_tokens + completion_tokens,
    }
