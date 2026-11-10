"""The text the external-evidence gate judges is what the user wrote, not a notice the runtime appended behind it."""

from __future__ import annotations

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage

from myrm_agent_harness.agent.middlewares.completion.completion_guard.external_evidence import (
    build_external_evidence_reason,
    extract_latest_human_text,
)
from myrm_agent_harness.core.message_origin import runtime_human_message


def test_a_notice_behind_the_users_message_is_not_the_request() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="what is the weather in Paris today?"),
        AIMessage(content="checking"),
        runtime_human_message("[restore] 3 files were restored"),
    ]

    assert extract_latest_human_text(messages) == "what is the weather in Paris today?"


def test_the_latest_message_the_user_wrote_wins_over_an_earlier_one() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="first question"),
        AIMessage(content="answer"),
        HumanMessage(content="second question"),
        runtime_human_message("[hint] continue"),
    ]

    assert extract_latest_human_text(messages) == "second question"


def test_the_text_parts_of_a_multimodal_user_message_are_read_past_a_notice() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(
            content=[{"type": "text", "text": "look this up"}, {"type": "image_url", "image_url": {"url": "x"}}]
        ),
        runtime_human_message("[hint] continue"),
    ]

    assert extract_latest_human_text(messages) == "look this up"


def test_notices_alone_carry_no_request() -> None:
    assert extract_latest_human_text([runtime_human_message("[restore] files")]) is None


def test_a_notice_cannot_make_an_ordinary_request_demand_external_evidence() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="rename the helper in utils.py"),
        runtime_human_message("[notice] verify the latest news before you answer"),
    ]

    assert build_external_evidence_reason(messages=messages, records=[]) is None


def test_a_notice_cannot_hide_that_the_user_asked_for_fresh_information() -> None:
    messages: list[BaseMessage] = [
        HumanMessage(content="what is the latest news about the release?"),
        runtime_human_message("[restore] 3 files were restored"),
    ]

    reason = build_external_evidence_reason(messages=messages, records=[])

    assert reason is not None
    assert "what is the latest news about the release?" in reason
