"""L1 function index: the callable functions of a PTC-routed MCP skill, listed in its own catalog entry.

[INPUT]
- backends.skills.types::SkillMetadata (POS: ``mcp.inline_functions``, the names the generator allows inline; ``mcp.tools`` / ``mcp.tool_schemas`` for their documentation)
- agent.skills.mcp.schema_doc_utils (POS: JSON Schema to signature rendering)
- agent.skills.runtime.ptc_calling::CALL_SYNTAX / CALL_WORKFLOW (POS: the calling convention)
- backends.skills.scanning.scanner::scan_skill_content (POS: the load-time scan; a documented block it flags is not listed)
- utils.text_utils::get_token_count (POS: token estimate)

[OUTPUT]
- L1_FUNCTION_INDEX_MAX_TOKENS / L1_DOCUMENTED_INDEX_MAX_TOKENS: ceilings of all name lines / all documented blocks
- FunctionIndexes / fit_function_indexes(): the ``<functions>`` block of every entry whose index fits its ceiling
- function_index_rules(): the rule block that tells the model what a ``<functions>`` block allows

[POS]
A PTC-routed MCP server hides its functions behind ``skill_select_tool``, so even a task one function answers pays a
round just to learn the names, and another to learn the arguments. The catalog entry carries them instead. A server
whose whole documentation is small lists every function with its signature, description and parameter descriptions,
which is what a directly bound tool schema tells the model, so the model neither selects the skill nor reads a doc
file; any other server lists the names, and the rule block lets the model call them without selecting the skill;
selecting stays available for the full signatures. The descriptions a documented block shows are text the server
controls and the model reads before it selects anything, so a block the load-time scan flags as high-risk is not
listed: that server lists its names, as it would without documentation.

The lines are budgeted apart from the entries' ``L1_CATALOG_MAX_TOKENS``, like ``<hidden_skill_names>``: an index
can never push another skill's entry out of the catalog. An index is listed whole or not at all, because a partial
list would read as the complete list the rules promise.
"""

from __future__ import annotations

import logging
from collections.abc import Sequence
from functools import lru_cache
from typing import NamedTuple
from xml.sax.saxutils import escape

from myrm_agent_harness.agent.skills.mcp.schema_doc_utils import (
    normalize_input_schema,
    render_output_type,
    render_signature,
)
from myrm_agent_harness.agent.skills.mcp.tool_name_utils import build_tool_name_map
from myrm_agent_harness.agent.skills.runtime.ptc_calling import CALL_SYNTAX, CALL_WORKFLOW
from myrm_agent_harness.backends.skills.types import MCPSkillData, SkillMetadata
from myrm_agent_harness.utils.text_utils import get_token_count

logger = logging.getLogger(__name__)

L1_FUNCTION_INDEX_MAX_TOKENS = 1_200
"""Ceiling of all ``<functions>`` lines together; the lines ride in every turn's prompt, so the sum is bounded.

A name costs about 4 tokens (measured on a 100-tool server), so the ceiling holds roughly 300 names; longer names fit
fewer. A larger server keeps the select-first path, whose L2 document is built for it.
"""

L1_DOCUMENTED_INDEX_MAX_TOKENS = 2_400
"""Ceiling of all documented ``<functions>`` blocks together; a server whose documentation is larger lists names.

A documented tool costs 90-120 tokens (measured on the 12306 and Kubernetes mock servers: eight tools took 943 and 732
tokens, 60-70% of the same tools bound directly as JSON schemas), so the ceiling holds roughly twenty tools.
"""

DESCRIPTION_MAX_CHARS = 400
PARAM_DESCRIPTION_MAX_CHARS = 240
"""Characters of a function's / a parameter's description kept in a documented block (the rest is cut with ``...``)."""


def _rules(entry_sentence: str, docs_sentence: str | None) -> tuple[str, ...]:
    return (
        " <function_index_rules>",
        f" {entry_sentence} If they cover the request, skip skill_select_tool and call them from "
        "bash_code_execute_tool; this overrides any other rule to select a skill first. Below, <name> is the entry's name.",
        *(f" {line}" for line in CALL_SYNTAX.format(skill_name="<name>").splitlines()),
        *((docs_sentence,) if docs_sentence else ()),
        *(f" {line}" for line in CALL_WORKFLOW.splitlines()),
        " </function_index_rules>",
    )


FUNCTION_INDEX_RULES: tuple[str, ...] = _rules(
    "An entry with <functions> lists every function of that skill and can be used without selecting it.",
    " Docs: `/mcp/<name>/<function_name>.md` (arguments and return shape) — read it with `file_read_tool` only when a "
    "function's arguments are not obvious from its name, not before every call; select the skill instead when you "
    "need every signature at once.",
)
DOCUMENTED_INDEX_RULES: tuple[str, ...] = _rules(
    "An entry with <functions> lists every function of that skill with its signature, description and parameter "
    "descriptions, so it can be used without selecting it or reading its docs; a parameter marked `?` is optional.",
    None,
)


class FunctionIndexes(NamedTuple):
    """The ``<functions>`` block of each entry by skill name, and whether every block is a documented one."""

    blocks: dict[str, str]
    documented: bool


@lru_cache(maxsize=1024)
def _index_token_cost(rendered_index: str) -> int:
    return get_token_count(rendered_index)


def _render_function_index(function_names: Sequence[str]) -> str:
    return f" <functions>{', '.join(escape(name) for name in function_names)}</functions>"


def _one_line(text: object, limit: int) -> str:
    flat = " ".join(str(text or "").split())
    return flat if len(flat) <= limit else f"{flat[:limit].rstrip()}..."


@lru_cache(maxsize=256)
def _passes_load_time_scan(skill_name: str, documented: str) -> bool:
    """Whether a documented block is free of the high-risk findings the skill document is warned about at load time."""
    from myrm_agent_harness.backends.skills.scanning.scanner import ScanSeverity, scan_skill_content

    flagged = [
        finding
        for finding in scan_skill_content(skill_name, documented).findings
        if finding.severity >= ScanSeverity.HIGH
    ]
    if flagged:
        logger.warning(
            "MCP skill '%s' documents %d high-risk scan finding(s); its entry lists names only",
            skill_name,
            len(flagged),
        )
    return not flagged


def _render_documented_index(mcp: MCPSkillData) -> str:
    """The ``<functions>`` block with, per function, the signature, the description and every parameter's description."""
    name_map = build_tool_name_map(mcp.tools)
    lines: list[str] = []
    for tool in mcp.tools:
        schema = mcp.tool_schemas.get(tool, {})
        input_schema = normalize_input_schema(schema.get("inputSchema"))
        signature = render_signature(name_map[tool], input_schema)
        output_schema = schema.get("outputSchema")
        if isinstance(output_schema, dict) and output_schema:
            signature = f"{signature} -> {render_output_type(output_schema)}"
        lines.append(f"- {signature}")
        if description := _one_line(schema.get("description"), DESCRIPTION_MAX_CHARS):
            lines.append(f"    {description}")
        properties = input_schema.get("properties")
        for name, info in properties.items() if isinstance(properties, dict) else ():
            if isinstance(info, dict) and (text := _one_line(info.get("description"), PARAM_DESCRIPTION_MAX_CHARS)):
                lines.append(f"    {name}: {text}")
    body = "\n".join(f" {escape(line)}" for line in lines)
    return f" <functions>\n{body}\n </functions>"


def fit_function_indexes(skills: Sequence[SkillMetadata]) -> FunctionIndexes:
    """Rendered ``<functions>`` block per skill name, within the two ceilings.

    A skill whose documented block fits ``L1_DOCUMENTED_INDEX_MAX_TOKENS`` and passes the load-time scan is documented;
    any other lists its names if they fit ``L1_FUNCTION_INDEX_MAX_TOKENS``. Skills are taken in catalog order; one
    whose block no longer fits is skipped, and a later, shorter block may still fit.
    """
    names_left, documented_left = L1_FUNCTION_INDEX_MAX_TOKENS, L1_DOCUMENTED_INDEX_MAX_TOKENS
    fitted: dict[str, str] = {}
    all_documented = True
    for skill in skills:
        mcp = skill.mcp
        if mcp is None or not skill.available or not mcp.inline_functions:
            continue
        documented = _render_documented_index(mcp)
        if (cost := _index_token_cost(documented)) <= documented_left and _passes_load_time_scan(
            skill.name, documented
        ):
            fitted[skill.name] = documented
            documented_left -= cost
            continue
        names = _render_function_index(mcp.inline_functions)
        if (cost := _index_token_cost(names)) <= names_left:
            fitted[skill.name] = names
            names_left -= cost
            all_documented = False
    return FunctionIndexes(fitted, all_documented and bool(fitted))


def function_index_rules(indexes: FunctionIndexes) -> tuple[str, ...]:
    """The rule block for the blocks that were listed; empty when no entry has one."""
    if not indexes.blocks:
        return ()
    return DOCUMENTED_INDEX_RULES if indexes.documented else FUNCTION_INDEX_RULES


__all__ = [
    "DESCRIPTION_MAX_CHARS",
    "DOCUMENTED_INDEX_RULES",
    "FUNCTION_INDEX_RULES",
    "L1_DOCUMENTED_INDEX_MAX_TOKENS",
    "L1_FUNCTION_INDEX_MAX_TOKENS",
    "PARAM_DESCRIPTION_MAX_CHARS",
    "FunctionIndexes",
    "fit_function_indexes",
    "function_index_rules",
]
