"""Digests of a request's messages and where two requests stop sharing a prefix."""

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage

from myrm_agent_harness.agent.context_management.infra.prefix_chain import (
    PrefixShift,
    find_prefix_shift,
    message_digests,
)


def _conversation() -> list[BaseMessage]:
    return [
        HumanMessage(content="find the file"),
        AIMessage(content="", tool_calls=[{"name": "search", "args": {"q": "file"}, "id": "c1", "type": "tool_call"}]),
        ToolMessage(content="found a.py", tool_call_id="c1"),
    ]


class TestMessageDigests:
    def test_the_same_messages_give_the_same_digests_whatever_objects_hold_them(self) -> None:
        assert message_digests(_conversation()) == message_digests(_conversation())

    def test_one_digest_per_message(self) -> None:
        assert len(message_digests(_conversation())) == 3

    def test_a_cache_breakpoint_on_a_message_is_not_content(self) -> None:
        marked = _conversation()
        marked[2].additional_kwargs["cache_control"] = {"type": "ephemeral"}

        assert message_digests(marked) == message_digests(_conversation())

    def test_a_cache_breakpoint_inside_a_content_block_is_not_content(self) -> None:
        plain = [HumanMessage(content=[{"type": "text", "text": "hi"}])]
        marked = [HumanMessage(content=[{"type": "text", "text": "hi", "cache_control": {"type": "ephemeral"}}])]

        assert message_digests(marked) == message_digests(plain)

    def test_changed_text_changes_the_digest(self) -> None:
        edited = _conversation()
        edited[2] = ToolMessage(content="found b.py", tool_call_id="c1")

        before, after = message_digests(_conversation()), message_digests(edited)

        assert before[:2] == after[:2]
        assert before[2] != after[2]

    def test_the_author_of_a_text_is_part_of_the_digest(self) -> None:
        assert message_digests([HumanMessage(content="x")]) != message_digests([AIMessage(content="x")])

    def test_a_changed_tool_call_changes_the_digest(self) -> None:
        edited = _conversation()
        edited[1] = AIMessage(
            content="", tool_calls=[{"name": "search", "args": {"q": "other"}, "id": "c1", "type": "tool_call"}]
        )

        assert message_digests(edited)[1] != message_digests(_conversation())[1]

    def test_the_call_a_result_answers_is_part_of_the_digest(self) -> None:
        assert message_digests([ToolMessage(content="r", tool_call_id="c1")]) != message_digests(
            [ToolMessage(content="r", tool_call_id="c2")]
        )

    def test_extra_fields_that_reach_the_wire_are_part_of_the_digest(self) -> None:
        plain = [AIMessage(content="answer")]
        reasoned = [AIMessage(content="answer", additional_kwargs={"reasoning_content": "thought"})]

        assert message_digests(reasoned) != message_digests(plain)

    def test_the_name_a_message_carries_is_part_of_the_digest(self) -> None:
        alice = [HumanMessage(content="x", name="alice")]

        assert message_digests(alice) != message_digests([HumanMessage(content="x", name="bob")])
        assert message_digests(alice) != message_digests([HumanMessage(content="x")])

    def test_an_empty_field_is_the_same_message_as_a_missing_one(self) -> None:
        # Falsy extras never reach the wire, so editing one into the other is no change to the prefix.
        assert message_digests([HumanMessage(content="x", name="")]) == message_digests([HumanMessage(content="x")])

    def test_content_blocks_are_told_apart_by_where_one_ends_and_the_next_begins(self) -> None:
        assert message_digests([HumanMessage(content=["ab", "c"])]) != message_digests(
            [HumanMessage(content=["a", "bc"])]
        )

    def test_the_order_of_keys_inside_a_content_block_is_not_content(self) -> None:
        tagged = [HumanMessage(content=[{"type": "text", "text": "hi"}])]
        reordered = [HumanMessage(content=[{"text": "hi", "type": "text"}])]

        assert message_digests(tagged) == message_digests(reordered)

    def test_text_no_encoder_accepts_still_has_a_digest(self) -> None:
        assert len(message_digests([HumanMessage(content="broken \ud800 text")])) == 1

    def test_a_block_json_cannot_order_still_has_a_stable_digest(self) -> None:
        odd = [HumanMessage(content=[{1: "a", "b": 2}])]

        assert message_digests(odd) == message_digests([HumanMessage(content=[{1: "a", "b": 2}])])


class TestFindPrefixShift:
    def test_a_request_that_only_appends_shifts_nothing(self) -> None:
        assert find_prefix_shift(("a", "b"), ("a", "b", "c"), announced=False) is None

    def test_a_repeated_request_shifts_nothing(self) -> None:
        assert find_prefix_shift(("a", "b"), ("a", "b"), announced=False) is None

    def test_the_first_edited_message_is_named(self) -> None:
        shift = find_prefix_shift(("a", "b", "c"), ("a", "x", "c", "d"), announced=False)

        assert shift is not None
        assert shift == PrefixShift(first_index=1, previous_length=3, current_length=4, announced=False)
        assert not shift.truncated

    def test_a_message_inserted_before_the_end_moves_everything_behind_it(self) -> None:
        shift = find_prefix_shift(("a", "b", "c"), ("a", "n", "b", "c"), announced=False)

        assert shift is not None
        assert shift.first_index == 1

    def test_a_dropped_tail_is_a_truncation(self) -> None:
        shift = find_prefix_shift(("a", "b", "c"), ("a", "b"), announced=False)

        assert shift is not None
        assert shift == PrefixShift(first_index=2, previous_length=3, current_length=2, announced=False)
        assert shift.truncated

    def test_the_announcement_of_a_rewrite_is_carried_on_the_shift(self) -> None:
        shift = find_prefix_shift(("a", "b"), ("a", "x"), announced=True)

        assert shift is not None
        assert shift.announced

    def test_the_record_of_a_shift_is_json_simple(self) -> None:
        rewritten = find_prefix_shift(("a", "b"), ("a", "x"), announced=True)
        truncated = find_prefix_shift(("a", "b"), ("a",), announced=False)

        assert rewritten is not None and truncated is not None
        assert rewritten.as_record() == {
            "first_index": 1,
            "previous_length": 2,
            "current_length": 2,
            "kind": "rewritten",
            "announced": True,
        }
        assert truncated.as_record()["kind"] == "truncated"
