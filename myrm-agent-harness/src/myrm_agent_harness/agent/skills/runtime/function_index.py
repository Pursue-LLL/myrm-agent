"""L1 function index: the callable names of a PTC-routed MCP skill, listed in its own catalog entry.

[INPUT]
- backends.skills.types::SkillMetadata (POS: ``mcp.inline_functions``, the names the generator allows inline)
- agent.skills.runtime.ptc_calling::CALL_SYNTAX / CALL_WORKFLOW (POS: the calling convention)
- utils.text_utils::get_token_count (POS: token estimate)

[OUTPUT]
- L1_FUNCTION_INDEX_MAX_TOKENS: ceiling of all ``<functions>`` lines together
- fit_function_indexes(): the ``<functions>`` line of every entry whose list fits the ceiling
- FUNCTION_INDEX_RULES: the rule block that tells the model what a ``<functions>`` line allows

[POS]
A PTC-routed MCP server hides its functions behind ``skill_select_tool``, so even a task one function answers pays a
round just to learn the names. The catalog entry carries the names instead, and the rule block lets the model call
them without selecting the skill; selecting stays available for the full signatures.

The lines are budgeted apart from the entries' ``L1_CATALOG_MAX_TOKENS``, like ``<hidden_skill_names>``: an index
can never push another skill's entry out of the catalog. An index is listed whole or not at all, because a partial
list would read as the complete list the rules promise.
"""

from __future__ import annotations

from collections.abc import Sequence
from functools import lru_cache
from xml.sax.saxutils import escape

from myrm_agent_harness.agent.skills.runtime.ptc_calling import CALL_SYNTAX, CALL_WORKFLOW
from myrm_agent_harness.backends.skills.types import SkillMetadata
from myrm_agent_harness.utils.text_utils import get_token_count

L1_FUNCTION_INDEX_MAX_TOKENS = 1_200
"""Ceiling of all ``<functions>`` lines together; the lines ride in every turn's prompt, so the sum is bounded.

A name costs about 4 tokens (measured on a 100-tool server), so the ceiling holds roughly 300 names; longer names fit
fewer. A larger server keeps the select-first path, whose L2 document is built for it.
"""

FUNCTION_INDEX_RULES: tuple[str, ...] = (
    " <function_index_rules>",
    " An entry with <functions> lists every function of that skill and can be used without selecting it. If they "
    "cover the request, skip skill_select_tool and call them from bash_code_execute_tool; this overrides any other "
    "rule to select a skill first. Below, <name> is the entry's name.",
    *(f" {line}" for line in CALL_SYNTAX.format(skill_name="<name>").splitlines()),
    " Docs: `/mcp/<name>/<function_name>.md` — read it with `file_read_tool` for the arguments and return shape of "
    "the one or two functions you will call; select the skill instead when you need every signature at once.",
    *(f" {line}" for line in CALL_WORKFLOW.splitlines()),
    " </function_index_rules>",
)


@lru_cache(maxsize=1024)
def _index_token_cost(rendered_index: str) -> int:
    return get_token_count(rendered_index)


def _render_function_index(function_names: Sequence[str]) -> str:
    return f" <functions>{', '.join(escape(name) for name in function_names)}</functions>"


def fit_function_indexes(skills: Sequence[SkillMetadata]) -> dict[str, str]:
    """Rendered ``<functions>`` line per skill name, within ``L1_FUNCTION_INDEX_MAX_TOKENS``.

    Skills are taken in catalog order; one whose list no longer fits is skipped, and a later, shorter list may still fit.
    """
    remaining = L1_FUNCTION_INDEX_MAX_TOKENS
    fitted: dict[str, str] = {}
    for skill in skills:
        if skill.mcp is None or not skill.available or not skill.mcp.inline_functions:
            continue
        rendered = _render_function_index(skill.mcp.inline_functions)
        cost = _index_token_cost(rendered)
        if cost <= remaining:
            fitted[skill.name] = rendered
            remaining -= cost
    return fitted


__all__ = ["FUNCTION_INDEX_RULES", "L1_FUNCTION_INDEX_MAX_TOKENS", "fit_function_indexes"]
