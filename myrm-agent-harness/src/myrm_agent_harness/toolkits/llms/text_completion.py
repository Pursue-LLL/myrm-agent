"""One-shot text completion outside the chat-model stack.

[INPUT]
- transport::get_transport (POS: provider-agnostic chat completion)
- utils.chat_utils::extract_completion_text (POS: answer text of an OpenAI-shaped completion)

[OUTPUT]
- acomplete_text: the answer text of one plain chat request

[POS]
For single utility requests that need no streaming, tools or history (an eval judge, a spoken-summary rewrite, a
policy draft): one request, the model's answer as stripped text. It bypasses the chat adapter, so it also bypasses
the outbound privacy guard that lives there: callers must decide that consciously, and the server lists each
one in its architecture test.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from myrm_agent_harness.toolkits.llms.transport import get_transport
from myrm_agent_harness.utils.chat_utils import extract_completion_text


async def acomplete_text(
    model: str,
    messages: Sequence[Mapping[str, object]],
    *,
    api_key: str | None = None,
    api_base: str | None = None,
    temperature: float | None = None,
    max_tokens: int | None = None,
    timeout: float | None = None,
) -> str:
    """The stripped answer of ``model`` to ``messages`` (empty when the model returned no text)."""
    params: dict[str, object] = {
        "model": model,
        "api_key": api_key,
        "api_base": api_base,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "timeout": timeout,
    }
    response = await get_transport().acompletion(
        messages=messages, **{key: value for key, value in params.items() if value is not None}
    )
    return extract_completion_text(response).strip()
