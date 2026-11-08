"""How the model calls a PTC-routed MCP function: one text behind the L1 function index and the L2 skill document.

[INPUT]
(none: constant text)

[OUTPUT]
- CALL_SYNTAX: the import / await / keyword-argument rule, written for one skill's import name (``{skill_name}``)
- CALL_WORKFLOW: how many bash blocks a task gets, what each block prints, how Python literals are spelled

[POS]
The calling convention is told twice: the L1 catalog gives it once for every entry that lists its functions
(``function_index``), and the generated L2 skill document gives it for the one skill the model selected
(``agent/skills/mcp/core_generator.py``). Both embed these constants, so the two texts cannot drift apart.
"""

from __future__ import annotations

CALL_SYNTAX = (
    "Import: `from skills.{skill_name} import <func_name>` (`skills.*` = MCP; `tools.*` = built-in; NOT interchangeable).\n"
    "Import every function you call before awaiting it. MCP functions are async: always `await` every call; "
    "a call without `await` returns a coroutine, not data.\n"
    "Args: **always call with keyword arguments** — `func(param=value)`."
)

CALL_WORKFLOW = (
    "Use ONE `bash_code_execute_tool` per task by default. Batch every call that can run in that block, including "
    "independent calls and calls whose exact return shape is unknown: await them, print each real result as "
    "`[OBSERVATION]`, then continue inside the same block. Split into a second bash ONLY when a later call's "
    "arguments genuinely cannot be written without first seeing an earlier result; then print the actual returned "
    "value and continue. Do not split merely because a return shape is undocumented, and do not call a lookup tool "
    "just to discover a value the target already accepts. Results are parsed Python objects — do NOT `json.loads()`; "
    "only access fields explicitly documented. If a call fails, read the error and fix the arguments; do not repeat "
    "a call that already succeeded. Emit `[RESULT]` only after the last dependent call; use `[OBSERVATION]` for "
    "intermediate outputs.\n"
    "Python literals `None`/`True`/`False` (not null/true/false). If the tool signature lists `timeout`, "
    "pass `timeout=120`."
)

__all__ = ["CALL_SYNTAX", "CALL_WORKFLOW"]
