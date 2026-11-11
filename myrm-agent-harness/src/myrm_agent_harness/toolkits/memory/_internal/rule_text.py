"""A rule's text: its one display line, and the instruction inside a text that may already be a display line.

[INPUT]
- memory._internal.storage::MemoryRejectedError (POS: refusal whose message is addressed to the caller and shown as written.)

[OUTPUT]
- format_rule_content: the ``When: <trigger> → Do: <action>`` line a rule is stored and recalled as
- split_rule_text: the instruction, and the trigger the text names, inside a text that may be a display line
- rule_texts: the ``content`` and ``action`` to store for a rule saved with a trigger and an instruction
- RuleFields, edited_rule_fields: the trigger, action and content a rule holds, and what it holds once its text is replaced

[POS]
A rule is read twice: the prompt is built from its ``trigger`` and ``action`` fields, while recall and the WebUI show its
``content`` line. Recall prints ``When: … → Do: …``, so a model that writes that line back as a rule's text would wrap it
a second time, in the stored action and so in every prompt; an edit that replaced only ``content`` would leave the prompt
on the old action. Saving, editing and a reviewer's rewording of a queued rule all go through here so the two readings
stay one text. Only a rule whose content is the display line of its fields is edited through them: the content of other
rules (a pattern's title, extracted text) says nothing about which field it would replace.
"""

from __future__ import annotations

import re
from typing import NamedTuple

from myrm_agent_harness.toolkits.memory._internal.storage import MemoryRejectedError

_FLAGS = re.IGNORECASE | re.DOTALL
_ARROW = r"(?:→|->)"
# No ``\s*`` touches the lazy trigger group: padding it on both sides makes a long input cost cubic time.
_DISPLAY_LINE = re.compile(rf"\s*when:(?P<trigger>.+?){_ARROW}\s*do:\s*(?P<action>\S.*)", _FLAGS)
# One wrapper is peeled per pass; four cover a rule that was written back more than once.
_MAX_WRAPPERS = 4


class RuleFields(NamedTuple):
    trigger: str
    action: str
    content: str


def format_rule_content(trigger: str, action: str) -> str:
    return f"When: {trigger} → Do: {action}"


def _trigger_restated(trigger: str) -> re.Pattern[str] | None:
    """Match the trigger written out in front of the instruction (``When <trigger> → …``); None without a trigger."""
    trigger = trigger.strip()
    if not trigger:
        return None
    return re.compile(rf"\s*(?:when:?\s+)?{re.escape(trigger)}\s*{_ARROW}\s*(?:do:\s*)?(?P<action>\S.*)", _FLAGS)


def split_rule_text(text: str, trigger: str) -> tuple[str | None, str]:
    """Split ``text`` into the trigger it names and the instruction it holds.

    A display line (``When: … → Do: …``, however many times over) gives up its wrapper, and so does a text that starts
    with ``trigger`` and an arrow. Any other text comes back unchanged with no trigger. When several wrappers name a
    trigger, the outermost one is returned.
    """
    restated = _trigger_restated(trigger)
    written_trigger: str | None = None
    action = text
    for _ in range(_MAX_WRAPPERS):
        if line := _DISPLAY_LINE.match(action):
            written_trigger = written_trigger or line["trigger"].strip() or None
            action = line["action"].strip()
        elif restated is not None and (echo := restated.match(action)):
            action = echo["action"].strip()
        else:
            break
    return written_trigger, action


def rule_texts(trigger: str, action: str) -> tuple[str, str]:
    """The ``content`` and ``action`` to store for a rule saved with ``trigger`` and ``action``.

    The trigger the caller declared is authoritative: a display line written as the action only contributes its instruction.
    """
    _, instruction = split_rule_text(action, trigger)
    return format_rule_content(trigger, instruction), instruction


def edited_rule_fields(current: RuleFields, text: str) -> RuleFields:
    """The fields a rule holds once its text is replaced by ``text``: an instruction or a display line.

    The prompt reads ``trigger`` and ``action``, so replacing the text of a rule stored as its display line rewrites them
    and not only ``content``; a display line may also change the trigger. Any other content (a title, a summary, free text)
    is no function of the fields, so such a rule keeps its trigger and action and the text replaces only its content.
    """
    if not text.strip():
        raise MemoryRejectedError(
            "Not updated: the rule text is empty. Retry with the instruction the rule should enforce."
        )
    if current.content != format_rule_content(current.trigger, current.action):
        return current._replace(content=text)
    written_trigger, action = split_rule_text(text.strip(), current.trigger)
    trigger = written_trigger or current.trigger
    return RuleFields(trigger, action, format_rule_content(trigger, action))
