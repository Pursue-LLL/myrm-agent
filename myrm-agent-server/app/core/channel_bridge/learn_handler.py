"""ChannelLearnCommandHandler — /learn slash command handler.

Builds a structured prompt that instructs the agent to gather the source(s)
the user described and author a reusable SKILL.md, then saves it via the
existing `skill_manage_tool` tool.

[INPUT]
- channels.types::InboundMessage (POS: inbound message)
- channels.protocols.learn_command::LearnCommandHandler (POS: handler protocol)

[OUTPUT]
- ChannelLearnCommandHandler: LearnCommandHandler protocol implementation

[POS]
Business-layer handler for /learn. Rewrites the inbound message content
with a learn prompt and returns it for agent execution via SessionGate.
"""

from __future__ import annotations

import dataclasses
import re
from typing import Literal

from app.channels.types import InboundMessage

_InputType = Literal["url", "path", "text"]

_URL_PATTERN = re.compile(r"^https?://", re.IGNORECASE)
_PATH_PATTERN = re.compile(r"^[.~/]|[\\/]")

_AUTHORING_STANDARDS = """\
Follow the skill-authoring standards exactly:

Frontmatter (YAML between --- delimiters):
- name: lowercase-hyphenated, <=64 chars, no spaces.
- description: ONE sentence, <=60 characters. State the capability, not the \
implementation. No marketing words.
- version: 0.1.0

Body section order (omit a section only if it genuinely has no content):
1. "# <Human Title>" — 2-3 sentence intro: what it does, what it does NOT do.
2. "## When to Use" — bullet list of concrete trigger phrases.
3. "## Prerequisites" — env vars, install steps, credentials.
4. "## How to Run" — canonical invocation, framed through agent tools.
5. "## Quick Reference" — flat command/endpoint list, no narration.
6. "## Procedure" — numbered steps with exact commands.
7. "## Pitfalls" — known limits, things that look broken but aren't.
8. "## Verification" — a single command/check that proves the skill worked.

Quality bar:
- Prefer exact commands, URLs, function signatures that appear VERBATIM in the \
source. NEVER invent flags, paths, or APIs you didn't see.
- Keep it tight: ~100 lines for simple, ~200 for complex. Don't re-paste docs.
- Larger scripts belong in a separate file (add via `skill_manage_tool` \
action="write_file"), referenced from SKILL.md by relative path — not inlined."""


def _detect_input_type(user_args: str) -> _InputType:
    """Detect whether the user input is a URL, file path, or free-text."""
    stripped = user_args.strip()
    if _URL_PATTERN.match(stripped):
        return "url"
    if _PATH_PATTERN.match(stripped) and " " not in stripped.split("/")[0]:
        return "path"
    return "text"


def _build_learn_prompt(user_args: str) -> str:
    """Build the agent prompt for an open-ended /learn request."""
    input_type = _detect_input_type(user_args)

    if input_type == "url":
        gather_hint = (
            "The user provided a URL. Use `web_search_tool` or browser tools "
            "to fetch and read the page content. Extract the key procedures, "
            "commands, and configuration from the documentation."
        )
    elif input_type == "path":
        gather_hint = (
            "The user provided a file/directory path. Use `file_read_tool` "
            "or `grep_tool`/`glob_tool` to read the source code or "
            "documentation. Analyze the structure and extract reusable "
            "procedures."
        )
    else:
        gather_hint = (
            "The user provided a free-text description. If they referred to "
            "something done earlier in this conversation, review the "
            "conversation history. If they described a workflow, distill "
            "the steps into a reusable skill."
        )

    return (
        "[/learn] The user wants you to learn a reusable skill from the "
        "source(s) described below, and save it.\n\n"
        f"WHAT TO LEARN FROM:\n{user_args}\n\n"
        f"INPUT TYPE: {input_type}\n"
        f"{gather_hint}\n\n"
        "INSTRUCTIONS:\n"
        "1. Gather the material using the tools you already have.\n"
        "2. Author ONE SKILL.md following the standards below.\n"
        "3. Save it with the `skill_manage_tool` (action=\"save\"). "
        "Pick a sensible name (lowercase-hyphenated).\n\n"
        f"{_AUTHORING_STANDARDS}\n\n"
        "When done, tell the user:\n"
        "- The skill name\n"
        "- A one-line summary of what it captured\n"
        "- How to invoke it (e.g. via /command binding or [use skill-name])"
    )


class ChannelLearnCommandHandler:
    """Builds a learn prompt and injects it into the inbound message."""

    async def __call__(
        self,
        msg: InboundMessage,
        user_args: str,
    ) -> InboundMessage | None:
        args = user_args.strip()
        if not args:
            args = (
                "the workflow we just went through in this conversation — "
                "review the steps taken and distill them into a reusable skill"
            )

        content = _build_learn_prompt(args)
        return dataclasses.replace(msg, content=content)
