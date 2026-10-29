"""A message that carries a lone surrogate is still answered by a real provider.

[INPUT]
- ChatLiteLLM with the LITE model of ``.env.test`` (POS: the chat model every agent turn calls, a real provider call)

[OUTPUT]
- Fails when the call raises on the unpaired half of an emoji or when the model does not answer.

[POS]
A lone surrogate comes from text a repository, a web page or a tool result hands the agent, for example a name that is not valid
UTF-8 or a JSON escape such as ``\\ud83d`` that is not followed by its pair. It cannot be written as UTF-8, so the request body
cannot be built from it; the chat model replaces it before the request is made.
"""

from __future__ import annotations

import os

import pytest
from langchain_core.messages import HumanMessage
from myrm_agent_harness.toolkits.llms import ChatLiteLLM

from tests.api.agent.utils import get_lite_model_selection

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(not os.environ.get("LITE_API_KEY"), reason="E2E test requires LITE_API_KEY"),
    pytest.mark.timeout(120, method="thread"),
]


@pytest.mark.asyncio
@pytest.mark.parametrize("compatible", [False, True], ids=["native_route", "openai_compatible_route"])
async def test_a_message_with_an_unpaired_half_of_an_emoji_is_answered(compatible: bool) -> None:
    """The LITE model is called through its own LiteLLM route and through the OpenAI-compatible route a custom provider takes."""
    selection = get_lite_model_selection()
    native = str(selection["model"])
    route = f"openai/{native.split('/', 1)[1]}" if compatible else native
    llm = ChatLiteLLM(model=route, api_key=os.environ["LITE_API_KEY"], api_base=selection["baseUrl"])
    lone_surrogate = chr(0xD83D)
    with pytest.raises(UnicodeEncodeError):
        lone_surrogate.encode("utf-8")

    reply = await llm.ainvoke(
        [HumanMessage(content=f"Reply with the single word PONG. A stray half of an emoji follows: {lone_surrogate}")]
    )

    assert "PONG" in str(reply.content).upper()
