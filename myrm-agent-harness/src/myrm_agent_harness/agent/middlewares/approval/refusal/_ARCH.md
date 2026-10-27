# approval/refusal/

## Overview
How an approval refusal reaches the model. A refused tool call stays in the AI message and is answered by an error ToolMessage, so the model reads who refused it and why as the result of its own call; the wording says who refused (a policy, a person, an approval timeout) and what to do next. The package holds text and message bookkeeping only: the counters and thresholds live in `../helpers.py`, the decision branches in `../_batch_decisions.py`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Facade. The approval middleware and `helpers.py` import from here, never from a submodule. | — |
| `answered_calls.py` | Core | `answered_call_ids` — the calls of an AI message that a ToolMessage after it already answers (an earlier guard refused them; they are not put to a person again). `kept_tool_calls` — the calls the AI message keeps once some were approved, edited or refused: each approved call in its approved form, each answered call as it is, any other call dropped (fail closed). | ✅ |
| `answer.py` | Core | `refusal_answer` — the one constructor of the error ToolMessage that answers a refused call; it carries `additional_kwargs["error_category"]` for who refused (`DenialCause` → `policy_denied` / `user_declined` / `approval_timeout`), so the stream and the UI name the refuser instead of attributing the failure to the built-in tool. `rejection_cause` — a decision the approval timer settled (`timed_out`) is a timeout, any other rejection a person's. | ✅ |
| `wording.py` | Core | `DenialCause` (policy / user / timeout) picks the `[System: ...]` note appended to a refusal; `rejection_message` words a person's refusal (their reason) or an approval that timed out (nobody answered); `denial_hint` escalates the note once a denial counter is breached (attended: auto-mode suspended; unattended cron job: stop retrying and report). Notes open with `core.security.model_directed_notes.SYSTEM_NOTE_OPEN`, so the streaming layer can cut them from what a person sees. | ✅ |

## Layering
```
answer.py           → langchain_core.messages, utils.errors, wording
answered_calls.py   → langchain_core.messages
wording.py          → core.security.model_directed_notes
__init__.py         → answer, answered_calls, wording
```
Consumers: `../middleware.py` (answered-call filter, post-interrupt merge, the refusals it gives itself), `../_batch_decisions.py` (every refusal that follows a decision), `../helpers.py` (`record_denial`, `record_rejection`).
