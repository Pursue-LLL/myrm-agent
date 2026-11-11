"""A rule's text has one reading: the display line it is recalled as is never written into its action twice.

Recall prints a rule as ``When: <trigger> → Do: <action>`` and models write that line back as the rule's text, or restate
the trigger in front of the instruction. The helpers split such a text into the instruction it holds, and what a rule
holds after an edit follows the same split. Every case states the text the model wrote and the instruction that must remain.
"""

from __future__ import annotations

import time

import pytest

from myrm_agent_harness.toolkits.memory._internal.rule_text import (
    RuleFields,
    edited_rule_fields,
    format_rule_content,
    rule_texts,
    split_rule_text,
)
from myrm_agent_harness.toolkits.memory._internal.storage import MemoryRejectedError

TRIGGER = "when editing tests"
ACTION = "Run the whole test suite before committing"
LINE = f"When: {TRIGGER} → Do: {ACTION}"
REWORDED = "Run only the tests that touch the changed files"


def nested(depth: int) -> str:
    text = ACTION
    for _ in range(depth):
        text = f"When: {TRIGGER} → Do: {text}"
    return text


def held(*, content: str, trigger: str = TRIGGER, action: str = ACTION) -> RuleFields:
    return RuleFields(trigger, action, content)


# Texts that are a display line: (text, the trigger the text names).
_DISPLAY_LINES: dict[str, tuple[str, str]] = {
    "display-line": (LINE, TRIGGER),
    "ascii-arrow": (f"When: {TRIGGER} -> Do: {ACTION}", TRIGGER),
    "upper-case": (f"WHEN: {TRIGGER} → DO: {ACTION}", TRIGGER),
    "spacing": (f"  When:  {TRIGGER}  →  Do:   {ACTION}  \n", TRIGGER),
    "written-back-twice": (nested(2), TRIGGER),
    "written-back-four-times": (nested(4), TRIGGER),
    "outermost-trigger": (f"When: before any commit → Do: {LINE}", "before any commit"),
    "restated-trigger-inside": (f"When: {TRIGGER} → Do: When editing tests → {ACTION}", TRIGGER),
}

# Texts that restate the declared trigger in front of the instruction.
_RESTATED: dict[str, str] = {
    "without-do": f"When editing tests → {ACTION}",
    "with-do": f"When editing tests → Do: {ACTION}",
    "ascii-arrow": f"when editing tests -> {ACTION}",
}

_KEPT_AS_WRITTEN: dict[str, str] = {
    "plain-instruction": ACTION,
    "plain-instruction-keeps-its-spacing": f"  {ACTION}  ",
    "arrow-inside-the-instruction": "Run the unit tests → then the integration tests",
    "another-trigger-is-not-this-ones-echo": "When committing → run the tests",
    "display-line-with-no-instruction": "When: before any commit → Do:",
    "trigger-with-no-instruction": "When editing tests →",
    "chinese-instruction": "提交前运行完整测试套件",
    "chinese-echo-of-an-english-trigger": "当编辑测试时 → 提交前运行完整测试套件",
}


@pytest.mark.parametrize(("text", "named"), list(_DISPLAY_LINES.values()), ids=list(_DISPLAY_LINES))
def test_a_display_line_gives_up_its_wrapper_and_names_its_trigger(text: str, named: str) -> None:
    assert split_rule_text(text, TRIGGER) == (named, ACTION)


@pytest.mark.parametrize("text", list(_RESTATED.values()), ids=list(_RESTATED))
def test_a_trigger_written_in_front_of_the_instruction_is_dropped(text: str) -> None:
    assert split_rule_text(text, TRIGGER) == (None, ACTION)


def test_a_trigger_without_the_word_when_is_found_behind_one() -> None:
    assert split_rule_text(f"When editing tests → {ACTION}", "editing tests") == (None, ACTION)


@pytest.mark.parametrize("text", list(_KEPT_AS_WRITTEN.values()), ids=list(_KEPT_AS_WRITTEN))
def test_any_other_text_comes_back_unchanged(text: str) -> None:
    assert split_rule_text(text, TRIGGER) == (None, text)


def test_splitting_what_was_split_changes_nothing() -> None:
    texts = [text for text, _ in _DISPLAY_LINES.values()] + list(_RESTATED.values())
    for text in texts:
        _, instruction = split_rule_text(text, TRIGGER)
        assert split_rule_text(instruction, TRIGGER) == (None, instruction)


def test_only_four_wrappers_are_peeled() -> None:
    assert split_rule_text(nested(5), TRIGGER) == (TRIGGER, LINE)


def test_a_trigger_is_matched_literally() -> None:
    assert split_rule_text("When v1.2 (beta) → Run it", "v1.2 (beta)") == (None, "Run it")
    assert split_rule_text("When v1x2 (beta) → Run it", "v1.2 (beta)") == (None, "When v1x2 (beta) → Run it")


def test_a_blank_trigger_finds_nothing_to_drop() -> None:
    assert split_rule_text("→ Run the tests", "  ") == (None, "→ Run the tests")


@pytest.mark.parametrize(
    "text",
    [
        "When:" + " " * 3000,
        "When:" + "→ " * 3000,
        "When:" + ("→" + " " * 100) * 30,
        "When: " + "a " * 3000 + "→ nothing",
        "When: x → Do:" + " " * 3000,
    ],
    ids=["spaces", "arrows", "arrows-and-spaces", "long-trigger", "empty-instruction"],
)
def test_a_long_input_costs_linear_time(text: str) -> None:
    started = time.perf_counter()
    split_rule_text(text, TRIGGER)
    # A pattern that pads the trigger with whitespace on both sides needs tens of seconds for these.
    assert time.perf_counter() - started < 2.0


def test_the_display_line_joins_trigger_and_action() -> None:
    assert format_rule_content(TRIGGER, ACTION) == LINE


def test_a_plain_instruction_is_stored_as_it_always_was() -> None:
    assert rule_texts(TRIGGER, ACTION) == (LINE, ACTION)


@pytest.mark.parametrize("written", [LINE, nested(3), f"When editing tests → {ACTION}"], ids=["line", "nested", "echo"])
def test_a_display_line_saved_as_the_action_is_not_wrapped_again(written: str) -> None:
    assert rule_texts(TRIGGER, written) == (LINE, ACTION)


def test_the_trigger_the_caller_declared_wins_over_the_one_in_the_text() -> None:
    assert rule_texts("when committing", LINE) == (f"When: when committing → Do: {ACTION}", ACTION)


def test_an_edit_rewrites_the_action_and_keeps_the_display_line_of_a_rule_that_has_one() -> None:
    edited = edited_rule_fields(held(content=LINE), REWORDED)

    assert edited == RuleFields(TRIGGER, REWORDED, f"When: {TRIGGER} → Do: {REWORDED}")


def test_an_edit_written_as_a_display_line_can_change_the_trigger() -> None:
    edited = edited_rule_fields(held(content=LINE), f"When: before any commit → Do: {REWORDED}")

    assert edited == RuleFields("before any commit", REWORDED, f"When: before any commit → Do: {REWORDED}")


def test_an_edit_that_restates_the_trigger_leaves_the_instruction_alone() -> None:
    edited = edited_rule_fields(held(content=LINE), f"When editing tests → {REWORDED}")

    assert edited == RuleFields(TRIGGER, REWORDED, f"When: {TRIGGER} → Do: {REWORDED}")


def test_an_edit_trims_the_surrounding_whitespace_of_the_instruction() -> None:
    assert edited_rule_fields(held(content=LINE), f"  {REWORDED}\n").action == REWORDED


def test_an_edit_heals_a_rule_that_was_stored_wrapped_twice() -> None:
    garbled = held(content=format_rule_content(TRIGGER, LINE), action=LINE)

    assert edited_rule_fields(garbled, REWORDED) == RuleFields(TRIGGER, REWORDED, f"When: {TRIGGER} → Do: {REWORDED}")


# Content that is no function of the fields: a pattern's title, an "Avoid …" line a consolidation wrote.
_OWN_CONTENT = {"title": "Test discipline", "avoid-line": "Avoid pytest -x: run the whole suite"}


@pytest.mark.parametrize("content", _OWN_CONTENT.values(), ids=_OWN_CONTENT)
@pytest.mark.parametrize(
    "text",
    [REWORDED, f"When: before any commit → Do: {REWORDED}", f"  {REWORDED}\n"],
    ids=["instruction", "display-line", "padded"],
)
def test_a_rule_whose_content_is_not_its_display_line_keeps_its_fields_and_takes_the_text_as_written(
    content: str, text: str
) -> None:
    assert edited_rule_fields(held(content=content), text) == RuleFields(TRIGGER, ACTION, text)


@pytest.mark.parametrize("content", [LINE, *_OWN_CONTENT.values()], ids=["display-line", *_OWN_CONTENT])
@pytest.mark.parametrize("text", ["", "   ", "\n\t "], ids=["empty", "spaces", "whitespace"])
def test_an_empty_rule_text_is_refused_with_a_way_forward(content: str, text: str) -> None:
    with pytest.raises(MemoryRejectedError, match=r"^Not updated: the rule text is empty\. Retry with the instruction"):
        edited_rule_fields(held(content=content), text)
