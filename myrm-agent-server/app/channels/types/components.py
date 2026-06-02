"""Interactive UI component types for cross-channel message abstraction.

[INPUT]
(No external dependencies, pure data type definitions)

[OUTPUT]
- ActionButton, QuickReply, SelectMenu, ComponentRow: 交互Component
- ToolStep: ToolExecuteStep
- render_components_as_text, render_quick_replies_as_text: textdegradation渲染（Support in 英文国际化）

[POS]
UI component type definitions. Cross-channel interactive component abstractions for buttons, quick replies, and select menus.

"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.channels.i18n import channel_t


class ButtonStyle(StrEnum):
    """Visual style for an interactive button."""

    DEFAULT = "default"
    PRIMARY = "primary"
    DANGER = "danger"


@dataclass(frozen=True, slots=True)
class ActionButton:
    """An interactive button that triggers a callback via action_id.

    ``action_id`` format: ``{namespace}:{action}:{payload}``
    e.g. ``approval:approve:req-abc123``

    When ``url`` is set, the button opens the URL instead of triggering a
    callback (used by platforms like Telegram for inline URL buttons).
    """

    label: str
    action_id: str
    style: ButtonStyle = ButtonStyle.DEFAULT
    value: str = ""
    url: str = ""


@dataclass(frozen=True, slots=True)
class QuickReply:
    """A quick-reply chip that sends ``text`` as a new message when tapped.

    Unlike ActionButton, this does NOT trigger a callback — it simply
    injects ``text`` into the conversation as if the user typed it.

    When ``required`` is True, the quick reply is rendered as a text
    fallback on channels that lack native button support (e.g. approval
    prompts). Non-required quick replies are silently dropped during
    downgrade — they only appear on channels with native rendering.
    """

    label: str
    text: str
    required: bool = False


@dataclass(frozen=True, slots=True)
class SelectOption:
    """A single option within a SelectMenu."""

    label: str
    value: str
    description: str = ""


@dataclass(frozen=True, slots=True)
class SelectMenu:
    """A dropdown/list selector that triggers a callback on selection.

    ``action_id`` receives the selected ``SelectOption.value``.
    """

    action_id: str
    placeholder: str
    options: tuple[SelectOption, ...]


ComponentRow = tuple[ActionButton | SelectMenu, ...]


@dataclass(frozen=True, slots=True)
class ToolStep:
    """A single tool execution step summary.

    Accumulated by ChannelAgentExecutor from Agent TASKS_STEPS events.
    Rendered by renderer based on RenderStyle.tool_summary_display.
    """

    name: str
    label: str
    detail: str | None = None


def render_components_as_text(
    components: tuple[ComponentRow, ...], *, locale: str = "en"
) -> str:
    """Render interactive components as plain-text fallback.

    Used by channels that do not support native interactive components.
    Generates human-readable instructions for interaction.

    Args:
        components: Tuple of component rows to render.
        locale: Language code for text rendering ("en" or "zh"). Defaults to "en"
            for framework-level internationalization compliance. Business layer can
            override via ``OutboundMessage.metadata["locale"]``.

    Returns:
        Formatted text listing available actions and options.
    """
    lines: list[str] = []
    for row in components:
        for comp in row:
            if isinstance(comp, ActionButton):
                if comp.url:
                    lines.append(f"• {comp.label} → {comp.url}")
                else:
                    cmd = (
                        comp.action_id.split(":", 1)[1]
                        if ":" in comp.action_id
                        else comp.action_id
                    )
                    lines.append(f"• {comp.label} → /{cmd}")
            elif isinstance(comp, SelectMenu):
                opts = ", ".join(o.label for o in comp.options)
                prefix = channel_t(locale, "component_options_prefix")
                lines.append(f"• {comp.placeholder or prefix}: {opts}")
    return "\n".join(lines)


def render_quick_replies_as_text(
    quick_replies: tuple[QuickReply, ...], *, locale: str = "en"
) -> str:
    """Render quick-reply chips as a numbered text list with reply instructions.

    Args:
        quick_replies: Tuple of quick-reply items to render.
        locale: Language code for instruction text ("en" or "zh"). Defaults to "en"
            for framework-level internationalization compliance. Business layer can
            override via ``OutboundMessage.metadata["locale"]``.

    Returns:
        Formatted text with numbered options and reply instructions.
    """
    items = "\n".join(f"{i + 1} {qr.label}" for i, qr in enumerate(quick_replies))
    instruction = channel_t(locale, "component_quick_reply_instruction")
    return f"{items}\n\n{instruction}"
