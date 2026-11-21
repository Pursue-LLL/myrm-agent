# approval/evaluation/

## Overview
Judging the tool calls of a model response exactly once, in a graph node of their own, ahead of the node that asks a person. An approval card is answered by resuming the node that raised it, and LangGraph resumes a node by running it again from its first line, so anything such a node did before `interrupt()` is done a second time. Judging a call has side effects: a reviewer-model call, the refusal counters, the approval rate limit. Left in the asking node they ran twice, and a reviewer that answered differently the second time could let a call through that the person had just refused. The verdicts are therefore made here, committed to a checkpointed state key, and only read by `../middleware.py`.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| `__init__.py` | Package | Facade. `ToolApprovalMiddleware` imports from here, never from a submodule. | — |
| `record.py` | Core | The stored verdicts: `ApprovalEvaluation` (refused calls and calls that wait for a person, tagged with the id of the model response they are about), `ApprovalEvaluationState` (the state schema that adds the private `approval_evaluation` and `approval_path_pins` keys, kept out of the graph's input and output), `PathPin` (the paths a file call names and the files they open) and the conversions to and from the tuples `batch_processor/` uses. Plain types only, so any checkpoint serializer stores them. | ✅ |
| `pins.py` | Core | The pin of a file call, read the same way when it is made and when it is checked. `build_path_pins(calls, workspace_root)` records, for each `file_read` / `file_write` call that has an id, the paths it names and the files they open: the engine's own judged targets (`judged_file_paths`) resolved with every link followed (`""` for a text no file can be named by). `pin_of(state, call_id)` reads one back from the graph state, `None` when there is none or it is malformed. `path_moved(pin, tool_name, args, workspace_root)` is the run-time check: the typed paths are unchanged yet the files now opened are not all among the pinned ones, a subset being fine because a file created in between opens the place its name always pointed at; a call whose typed paths differ was edited by the person and is not held to the original files. | ✅ |
| `target.py` | Core | `resolve_approval_target` — the latest model response with tool calls, minus the calls an earlier guard already answered, with the session context the calls are judged in (security config, session key, workspace, whether this is a scheduled run — by the job's config or a `cron:` session key, so the agents a job delegated to count too — and canonical argument hashes). Both approval nodes find their calls here, so they cannot disagree. | ✅ |
| `evaluator.py` | Core | `evaluate_target` — the pre-interrupt half of the approval flow: user-intent ledger, recent-call window (the calls that ran or are being judged; a refused call never ran, so it is left out — that the model keeps trying refused calls is the denial counters' business) and taint labels for the reviewer, `is_interactive` (not a cron run, not a shadow agent), `evaluate_tool_batch`, then the per-user approval rate limit (calls over the limit become refusals). | ✅ |
| `node.py` | Core | `ApprovalEvaluationMiddleware` — the `after_model` hook that runs `evaluate_target` and stores the result under `approval_evaluation`, and the pins of the response's file calls under `approval_path_pins` in the same update, before any of its calls has run. Does nothing when no call needs a verdict. | ✅ |

## Layering
```
record.py     → langchain (AgentState, OmitFromSchema), langchain_core.messages
target.py     → ..refusal, agent.security, middlewares._session_context
evaluator.py  → ..batch_processor, ..intent_ledger, ..rate_limiter, record, target
pins.py       → agent.security (judged_paths, path_rules, tool_registry), core.security (path, tool_registry), record
node.py       → evaluator, pins, record, target
__init__.py   → evaluator, node, pins, record, target
```
Consumers: `../middleware.py` (reads the stored verdicts, judges inline only when none were stored), `../path_pin_guard.py` (reads a call's pin and checks it before the call runs), `_internals/_agent_build.py` (registers `ApprovalEvaluationMiddleware` and `path_pin_guard`).

## Invariants
- Registered directly after `ToolApprovalMiddleware` in the middleware list. LangChain runs `after_model` hooks from the last middleware to the first, so a model response meets the completion guard, the clarification guard, this node and then the approval node.
- The stored verdicts belong to one model response: they carry its message id and the approval node uses them only when the id matches. A response without an id matches nothing.
- The approval node clears the key when it finishes, so verdicts do not ride along in every later checkpoint.
- The path pins are not cleared there: the calls they guard run after the approval node. Each response's node writes them afresh (a response with no file call writes an empty map), they are taken before any call of the response has run, and `../path_pin_guard.py` looks a call up by its id.
- When no verdicts were stored (a stack built without this node, a unit test calling the approval hook directly) the approval node judges the calls itself and logs a warning: that path is not safe across an approval pause. The shipped stack never takes it; `tests/agent/middlewares/test_shipped_stack_hook_order.py` pins the node order.
