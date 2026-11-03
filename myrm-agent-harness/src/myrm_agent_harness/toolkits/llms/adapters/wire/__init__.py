"""Wire transport utilities for TransportChatModel.

[INPUT]
- toolkits.llms.adapters.wire.normalizer::responses_dict_to_chat_completion,
  responses_event_to_completion_chunk (POS: Responses wire 响应归一化层)
- toolkits.llms.adapters.wire.params::build_responses_kwargs
  (POS: Responses wire 请求装配层)
- toolkits.llms.adapters.wire.responses_stream::ResponsesStreamState
  (POS: per-stream function-call bookkeeping of the Responses wire)
- toolkits.llms.adapters.wire.routing::resolve_wire (POS: effective wire protocol of a call)
- toolkits.llms.adapters.wire.translator::chat_messages_to_responses_input,
  resolve_min_output_tokens (POS: Responses wire 出站请求翻译层)

[OUTPUT]
- responses_dict_to_chat_completion / responses_event_to_completion_chunk / ResponsesStreamState
- build_responses_kwargs
- chat_messages_to_responses_input / resolve_min_output_tokens
- resolve_wire

[POS]
Public surface of the wire transport subpackage. Import from here rather than from the
individual modules so the internal module layout stays free to change. Harness-only
protocol layer; vendor routing tables live in server `app/core/wire/`.
"""

from myrm_agent_harness.toolkits.llms.adapters.wire.normalizer import (
    responses_dict_to_chat_completion,
    responses_event_to_completion_chunk,
)
from myrm_agent_harness.toolkits.llms.adapters.wire.params import build_responses_kwargs
from myrm_agent_harness.toolkits.llms.adapters.wire.responses_stream import ResponsesStreamState
from myrm_agent_harness.toolkits.llms.adapters.wire.routing import resolve_wire
from myrm_agent_harness.toolkits.llms.adapters.wire.translator import (
    chat_messages_to_responses_input,
    resolve_min_output_tokens,
)

__all__ = [
    "ResponsesStreamState",
    "build_responses_kwargs",
    "chat_messages_to_responses_input",
    "resolve_min_output_tokens",
    "resolve_wire",
    "responses_dict_to_chat_completion",
    "responses_event_to_completion_chunk",
]
