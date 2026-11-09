"""Budget rendering and prompt guidance helpers for memory context injection.

Applies one token/char budget across the memory sections and renders them as a Markdown body,
neutralizes the tag openers of stored text, and generates static search guidance and cold-start
discovery prompts.

[INPUT]
- agent.security.guards.prompt_budget::CHARS_PER_TOKEN, BudgetedSection (POS: Prompt budgeting data models)
- langchain.agents.middleware::ModelRequest (POS: Agent runtime request model)

[OUTPUT]
- render_budgeted_sections, RenderedSections: Apply the budget and render the sections as one Markdown body, with the item count each kept and the characters they use
- MEMORY_BLOCK_MAX_TOKENS, MEMORY_BLOCK_BUDGET_CHARS: The memory block's budget, in tokens and in characters
- escape_xml_item: XML item sanitization helper
- defang_markup: Tag-opener neutralization for stored text in the system-privileged block
- bound_tool_names: The one reader of the tool names a request binds (objects, name dicts, OpenAI function dicts)
- memory_search_tool_bound: Check if memory_search_tool is bound to the request
- memory_search_guidance: Retrieve guidance text for memory search
- memory_guidance_tail: Retrieve citation and search guidance tail
- build_cold_start_context: Construct cold-start discovery prompt
- COLD_START_CONTEXT: Cached default cold-start context

[POS]
Internal helper module for memory_context_format: one budget over the memory sections, tag-opener neutralization, and the search-guidance and cold-start prompt texts.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple

from myrm_agent_harness.agent.security.guards.prompt_budget import (
    CHARS_PER_TOKEN,
    BudgetedSection,
)

if TYPE_CHECKING:
    from langchain.agents.middleware import ModelRequest


def escape_xml_item(text: str) -> str:
    """Escape XML special characters for memory item text."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# The characters whose NFKC form is "<": fullwidth and small brackets open a tag for the model just as ASCII does.
_TAG_OPENERS = ("<", "\uff1c", "\ufe64")


def defang_markup(text: str) -> str:
    """Rewrite every tag opener in ``text`` to ``&lt;``, so a stored value can neither open nor close a tag.

    Unlike ``escape_xml_item`` it leaves ``&`` and ``>`` alone: the block is Markdown for the model, not XML, and
    escaping them would turn ordinary values such as ``a && b`` or ``?x=1&y=2`` into noise.

    Runs for every stored value on every model call, hence ``str.replace`` (one native scan per opener) rather than
    a ``str.translate`` table, which looks every character up in a Python dict.
    """
    for opener in _TAG_OPENERS:
        text = text.replace(opener, "&lt;")
    return text


# Token budget of the memory block's sections, and the same limit in characters: the block's budget gauge reads
# the characters the sections used against this limit.
MEMORY_BLOCK_MAX_TOKENS = 2500
MEMORY_BLOCK_BUDGET_CHARS = MEMORY_BLOCK_MAX_TOKENS * CHARS_PER_TOKEN


class RenderedSections(NamedTuple):
    """The rendered body, the item count each section kept, and the characters the kept sections use of the budget."""

    body: str
    accepted_by_title: dict[str, int]
    used_chars: int


def render_budgeted_sections(
    sections: list[BudgetedSection],
    *,
    max_tokens: int,
    truncation_message: str,
) -> RenderedSections:
    """Render ``sections`` as one Markdown body within a single char budget, lowest ``priority`` value first.

    Every section draws on the same budget. Items are kept in order until one does not fit; a section cut after
    keeping some items, or whose header does not fit, ends the render, while a section none of whose items fit is
    skipped. ``truncation_message`` closes the body when the budget cut anything.

    Reports the accepted item count per section title and the characters the kept sections use of the budget, so
    callers can say how many items actually reached the model instead of how many merely exist, and how full the
    budget is.
    """
    max_chars = max_tokens * CHARS_PER_TOKEN
    current_length = 0
    # ``current_length`` also holds the header of a section none of whose items fit; this counts what is rendered.
    used_chars = 0
    truncated = False

    blocks: list[str] = []
    accepted_by_title: dict[str, int] = {}

    for section in sorted(sections, key=lambda s: s.priority):
        if not section.items:
            continue
        header = f"## {section.title}\n"
        if current_length + len(header) > max_chars:
            truncated = True
            break
        section_start = current_length
        current_length += len(header)

        accepted_lines: list[str] = []
        for item in section.items:
            line = f"- {item}\n"
            if current_length + len(line) > max_chars:
                truncated = True
                break
            accepted_lines.append(line)
            current_length += len(line)

        if not accepted_lines:
            continue

        used_chars += current_length - section_start
        accepted_by_title[section.title] = accepted_by_title.get(section.title, 0) + len(accepted_lines)
        blocks.append(header + "".join(accepted_lines).strip())

        if truncated:
            break

    body = "\n\n".join(blocks).strip()
    if truncated and truncation_message and blocks:
        body = f"{body}\n{truncation_message.strip()}"

    return RenderedSections(body, accepted_by_title, used_chars)


def bound_tool_names(request: ModelRequest) -> frozenset[str]:
    """Names of the tools the request binds: tool objects, ``{"name": ...}`` dicts and OpenAI-style function dicts."""
    tools = getattr(request, "tools", None)
    if not isinstance(tools, (list, tuple, set, frozenset)):
        return frozenset()
    names: set[str] = set()
    for tool in tools:
        if isinstance(tool, dict):
            name = tool.get("name")
            if not isinstance(name, str):
                function = tool.get("function")
                name = function.get("name") if isinstance(function, dict) else None
        else:
            name = getattr(tool, "name", None)
        if isinstance(name, str):
            names.add(name)
    return frozenset(names)


def memory_search_tool_bound(request: ModelRequest) -> bool:
    """Detect if memory_search_tool is bound to the agent request."""
    return "memory_search_tool" in bound_tool_names(request)


def memory_search_guidance(*, memory_search_enabled: bool) -> str:
    """Memory-search tool guidance; empty when the tool is not bound.

    Names no corpus: which corpora exist depends on the agent's search policy, and the tool's own description
    and schema say so.
    """
    if not memory_search_enabled:
        return ""
    return "\n".join(
        [
            "## Memory Search",
            "Use memory_search_tool for durable user facts, preferences, profile data, rules, and project conventions.",
            (
                "Memories and recalled conversations are point-in-time records. "
                "If recalled info conflicts with current observations, trust what you see now."
            ),
        ]
    )


def memory_guidance_tail(*, memory_search_enabled: bool) -> str:
    """Shared guidance tail for warm memory contexts (citations + memory search)."""
    if not memory_search_enabled:
        return ""
    return f"""## Citation Requirements
When your answer directly relies on a memory or rule with an explicit [ID: ...] label (shown above), or on memory_search_tool results, you MUST append a citation tag at the end of the relevant sentence or paragraph.
Format: <cite:MEMORY_ID>
Example: "Based on your preference for concise answers <cite:mem-123>, here is the script."
Only cite an ID that is explicitly shown above or returned by memory_search_tool.

{memory_search_guidance(memory_search_enabled=memory_search_enabled)}"""


def build_cold_start_context(*, memory_search_enabled: bool) -> str:
    """Cold-start discovery context for a user with no memories yet."""
    return f"""<user_memory_context>
# New User — Discovery Mode

No memories yet. Actively learn about this user during the conversation:
- Note their name, role, and tech stack when mentioned
- Pay attention to how they prefer to receive information
- Observe recurring patterns in their requests
- Record explicit instructions about workflow, output format, or constraints

Use memory_save_tool to save important facts as you learn them.
{memory_guidance_tail(memory_search_enabled=memory_search_enabled)}
</user_memory_context>"""


COLD_START_CONTEXT = build_cold_start_context(memory_search_enabled=True)
