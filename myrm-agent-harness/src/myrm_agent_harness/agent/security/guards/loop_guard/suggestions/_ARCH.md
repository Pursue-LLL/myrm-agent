# suggestions/

## Overview

Suggestion generation subsystem for LoopGuard. Static `TOOL_SUGGESTIONS` in `core.py` plus dynamic generators per tool (web, file, browser snapshot, etc.).

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | Suggestion generation subsystem for LoopGuard. Analyzes parameters and | ✅ |
| bash.py | Core | Bash tool suggestions for loop detection. | ✅ |
| browser.py | Core | Browser tool suggestions for loop detection. | ✅ |
| core.py | Core | Core functions and static suggestions for loop detection. `evaluate_success_level` grades a result by the executor's verdict first (`errored` flag from an error-status ToolMessage is a failure; a bash command that closed its output block with no `[exit_code: N]` trailer exited 0), and otherwise reads only the first line of a data-returning tool's result for error wording (skill docs, file contents and query results carry error words that say nothing about the call). Bash that failed or whose exit is unknown, browser and write results are read whole. | ✅ |
| file.py | Core | File tool suggestions for loop detection. | ✅ |
| memory.py | Core | Memory tool suggestions for loop detection. | ✅ |
| meta.py | Core | Meta tool suggestions (subagent, skill) for loop detection. | ✅ |
| web.py | Core | Web tool suggestions for loop detection. | ✅ |
