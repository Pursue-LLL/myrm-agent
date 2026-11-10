# [POS]: tests/unit/toolkits/memory/test_human_tail_delta_injector.py
# [INPUT]: myrm_agent_harness.toolkits.memory.ephemeral_delta
# [OUTPUT]: Contract tests of the tail injector that places the active-delta block on the user's latest message

from __future__ import annotations

from langchain_core.messages import AIMessage, HumanMessage

from myrm_agent_harness.core.message_origin import runtime_human_message
from myrm_agent_harness.toolkits.memory.ephemeral_delta import EphemeralDeltaItem, HumanTailDeltaInjector

_IMAGE_PART = {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}
_DELTA = EphemeralDeltaItem(delta_id="d-1", target_key="port", content="use 8082")


def test_delta_injector_keeps_multimodal_parts_intact() -> None:
    message = HumanMessage(content=[{"type": "text", "text": "look"}, _IMAGE_PART])

    updated = HumanTailDeltaInjector().inject_deltas([message], [_DELTA])[-1]

    assert updated.content[1] == _IMAGE_PART
    assert "use 8082" in str(updated.content[-1])


def test_delta_block_lands_on_the_users_message_not_on_a_runtime_notice() -> None:
    notice = runtime_human_message("[constraint] no network")
    history = [HumanMessage(content="deploy it", id="u1"), AIMessage(content="working"), notice]

    out = HumanTailDeltaInjector().inject_deltas(history, [_DELTA])

    assert "use 8082" in str(out[0].content)
    assert out[-1] is notice
