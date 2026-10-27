"""A real ChatLiteLLM whose provider client records the text that would leave the process.

Privacy tests assert on the wire, not on a call site: whatever the code under test does, the messages handed to the
provider client are what a model provider would see.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from myrm_agent_harness.toolkits.llms.adapters.chat_model import ChatLiteLLM


def wire_llm(reply: str = "ok", *, reasoning: str | None = None) -> tuple[ChatLiteLLM, list[str]]:
    """A model and the list its provider client appends every outgoing message text to.

    ``reasoning`` is the reasoning trace a thinking model sends next to its answer.
    """
    sent: list[str] = []
    answer: dict[str, object] = {"role": "assistant", "content": reply}
    if reasoning is not None:
        answer["reasoning_content"] = reasoning

    async def acreate(*, messages: list[dict[str, object]], **_: object) -> dict[str, object]:
        sent.extend(str(message["content"]) for message in messages)
        return {
            "id": "chatcmpl-test",
            "model": "test-model",
            "choices": [{"index": 0, "finish_reason": "stop", "message": answer}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }

    model = ChatLiteLLM(model="openai/test-model")
    model.client = MagicMock()
    model.client.acreate = acreate
    return model, sent
