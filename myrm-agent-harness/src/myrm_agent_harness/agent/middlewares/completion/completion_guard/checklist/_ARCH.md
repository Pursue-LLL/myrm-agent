# checklist/

## Overview

The verification checklist of the completion guard: the rules that read a run's tool records in call order, and the
checklist text and critical causes built from them. The guard holds an answer back on the causes and, for a hold
with no other reason, shows the model the text.

## File & Submodule Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Facade | Public surface of the package (`assess_checklist`, `build_checklist`, `Checklist`, `CriticalCause`, `VERIFICATION_CAUSES`, `find_last_successful_verification_command`). | ✅ |
| `assessment.py` | Core | `assess_checklist()`: the checklist text and the `CriticalCause`s that hold an answer back (never verified, failed, empty or stale verification, a failure that still stands, unfinished todos), `build_checklist()` as the `(text, critical)` pair, and the last passing verification command for the re-run. The unfinished-todo check runs only for an agent that holds `todo_write`, on the running chat's own list; the list blocks finishing only once `file_write_tool` or `file_edit_tool` has run in the run, otherwise it is a WARNING line that never blocks and is read by the model only in the checklist the guard sends when it holds an answer back for a failed verification. | ✅ |
| `record_rules.py` | Core | The rules the verdict is made of, over the records in call order: code written and nothing after the last such write proved it (`code_changed_since_proof`), a verification category whose latest run failed (`failed_verification_types`), and failures after the last successful write that no identical later call put right (`unresolved_failures`; an exploratory failure before the work does not hold an answer back). Also what counts as a code file. | ✅ |

## Key Dependencies

- `agent.security.guards.loop_guard` — CallRecord, SuccessLevel, ToolGroup, VerificationCategory
- `agent.meta_tools.progress.storage` — the running chat's todo list (read lazily, only for an agent that keeps one)
