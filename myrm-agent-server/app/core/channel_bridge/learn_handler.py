"""ChannelLearnCommandHandler — /learn slash command handler.

Builds a structured prompt that instructs the agent to gather the source(s)
the user described and author a reusable SKILL.md, then saves it via the
existing `skill_manage_tool` tool.

[INPUT]
- channels.types::InboundMessage (POS: inbound message)
- channels.protocols.learn_command::LearnCommandHandler (POS: handler protocol)

[OUTPUT]
- ChannelLearnCommandHandler: LearnCommandHandler protocol implementation
- parse_learn_slash_args / rewrite_learn_query_if_needed: raw `/learn` detection and SSOT prompt rewrite (WebUI + channel)
- apply_learn_skill_manage_permission_overlay: per-turn skill_manage ASK elevation for learn authoring
- learn_authoring_prompt_text / is_learn_skill_authoring_prompt: force_skill_manage gate helpers

[POS]
Business-layer /learn SSOT. Builds the learn authoring prompt, rewrites raw WebUI slash input before agent execution, and aligns skill_manage permissions for this turn only.
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
- description: ONE sentence, **<=60 characters**, ends with a period. State the \
capability, not the implementation. No marketing words (powerful, comprehensive, \
seamless, advanced, robust). Do NOT repeat the skill name. After writing, COUNT \
characters; if over 60, shorten before saving.
    Good (<=60): `Search arXiv papers by keyword, author, or ID.`
    Bad (123 chars): `A comprehensive skill that lets the agent search arXiv for \
academic papers using keywords, authors, and categories.`
- version: 0.1.0
- platforms: optional list when the skill is platform-specific; omit when universal.
- Do NOT author hub/router/meta skills that only delegate to other skills.

Body section order (omit a section only if it genuinely has no content):
1. "# <Human Title>" — 2-3 sentence intro: what it does, what it does NOT do.
2. "## When to Use" — bullet list of concrete trigger phrases.
3. "## Prerequisites" — env vars, install steps, credentials.
4. "## How to Run" — canonical invocation, framed through agent tools.
5. "## Quick Reference" — flat command/endpoint list, no narration.
6. "## Procedure" — numbered steps with exact commands.
7. "## Pitfalls" — known limits, things that look broken but aren't.
8. "## Verification" — a single command/check that proves the skill worked.

Myrm-tool framing (this is what makes it a skill, not shell docs):
- Frame running scripts/commands as "invoke through `bash_code_execute_tool`".
- Reference Myrm tools by name in backticks: `file_read_tool`, `file_write_tool`, \
`file_edit_tool`, `grep_tool`, `glob_tool`, `web_search_tool`, `web_fetch_tool`, \
`bash_code_execute_tool`, `skill_manage_tool`, `delegate_task_tool`.
- Do NOT name shell utilities the agent already has wrapped: say `file_read_tool` \
not cat/head/tail, `grep_tool`/`glob_tool` not grep/rg/find/ls, `web_fetch_tool` \
not curl-to-scrape, `file_write_tool` not echo>file or heredocs.
- Third-party CLIs (ffmpeg, gh, an SDK) are fine inside a script file, but the \
prose still frames them as "invoke through `bash_code_execute_tool`".

Quality bar:
- Prefer exact commands, URLs, function signatures that appear VERBATIM in the \
source. NEVER invent flags, paths, or APIs you didn't see.
- Keep it tight: ~100 lines for simple, ~200 for complex. Don't re-paste docs.
- Larger scripts belong in a separate file (add via `skill_manage_tool` \
action="write_file"), referenced from SKILL.md by relative path — not inlined."""


LEARN_PROMPT_PREFIX = "[/learn]"
_LEARN_SLASH_COMMAND = "learn"
_DEFAULT_LEARN_ARGS = (
    "the workflow we just went through in this conversation — "
    "review the steps taken and distill them into a reusable skill"
)


def _extract_text_from_query(query: object) -> str | None:
    if isinstance(query, str):
        return query
    if isinstance(query, list):
        parts: list[str] = []
        for block in query:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        joined = "\n".join(parts)
        return joined if joined.strip() else None
    return None


def parse_learn_slash_args(query: object) -> str | None:
    """Return /learn trailing args when *query* is a raw slash message; else None."""
    text = _extract_text_from_query(query)
    if text is None:
        return None
    stripped = text.strip()
    if not stripped.startswith("/"):
        return None
    body = stripped[1:]
    if not body:
        return ""
    space_idx = body.find(" ")
    cmd_name = body[:space_idx].lower() if space_idx > 0 else body.lower()
    if cmd_name != _LEARN_SLASH_COMMAND:
        return None
    return body[space_idx + 1 :].strip() if space_idx > 0 else ""


def rewrite_learn_query_if_needed(query: object) -> object:
    """Rewrite raw WebUI/Chat ``/learn`` messages to the channel learn prompt SSOT."""
    if learn_authoring_prompt_text(query) is not None:
        return query
    args = parse_learn_slash_args(query)
    if args is None:
        return query
    return _build_learn_prompt(args)


def is_learn_skill_authoring_prompt(content: str) -> bool:
    """Return True when *content* is a /learn channel rewrite requiring skill_manage_tool."""
    stripped = content.strip()
    return stripped.startswith(LEARN_PROMPT_PREFIX) and "skill_manage_tool" in stripped


def learn_authoring_prompt_text(query: object) -> str | None:
    """Return the learn prompt text when *query* is a /learn authoring turn."""
    if isinstance(query, str):
        return query if is_learn_skill_authoring_prompt(query) else None
    if isinstance(query, list):
        parts: list[str] = []
        for block in query:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text", "")))
        joined = "\n".join(parts)
        return joined if is_learn_skill_authoring_prompt(joined) else None
    return None


def apply_learn_skill_manage_permission_overlay(
    security_config: dict[str, object] | None,
    *,
    query: object,
) -> dict[str, object] | None:
    """Elevate ``skill_manage`` to ASK for /learn turns that mount ``skill_manage_tool``.

    ``force_skill_manage`` mounts the write backend even when session presets such as
    ``explore`` deny ``skill_manage``. Align permissions for this turn only.
    """
    if learn_authoring_prompt_text(query) is None:
        return security_config
    merged = dict(security_config) if security_config else {}
    raw_permissions = merged.get("permissions")
    permissions: dict[str, object] = (
        {str(key): value for key, value in raw_permissions.items()}
        if isinstance(raw_permissions, dict)
        else {}
    )
    permissions["skill_manage"] = "ask"
    merged["permissions"] = permissions
    return merged


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
    args = user_args.strip() or _DEFAULT_LEARN_ARGS
    input_type = _detect_input_type(args)

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
        f"WHAT TO LEARN FROM:\n{args}\n\n"
        "The request may mix SOURCES (paths, URLs, pasted notes, \"what we just "
        "did\") and REQUIREMENTS (focus, scope, naming). Treat every part as "
        "load-bearing — prose after a URL or path is authoring guidance, not "
        "incidental. Never gather the first source and ignore the rest.\n\n"
        f"INPUT TYPE: {input_type}\n"
        f"{gather_hint}\n\n"
        "INSTRUCTIONS:\n"
        "1. Gather the material using the tools you already have.\n"
        "2. Author ONE SKILL.md following the standards below.\n"
        '3. Save it with the `skill_manage_tool` (action="save"). '
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
        content = _build_learn_prompt(user_args.strip())
        return dataclasses.replace(msg, content=content)
