"""The verification checklist: what the run's tool records say about its work, as text and as a verdict.

[INPUT]
- agent.middlewares.completion.completion_guard.checklist.record_rules::code_changed_since_proof, failed_verification_types, is_proof, unresolved_failures (POS: the rules the verdict is made of)
- agent.security.guards.loop_guard::CallRecord, ToolGroup, SuccessLevel (POS: loop guard types)

[OUTPUT]
- CriticalCause: why a run's work is not ready to hand in
- Checklist, assess_checklist(): the task-aware checklist text and the causes that hold an answer back
- build_checklist(): the same as a ``(text, has_critical_errors)`` pair
- find_last_successful_verification_command(): the last passing verification command, for the independent re-run

[POS]
Task-aware checklist generation for CompletionGuard. Work is critical only when the run wrote something that its
verification, failures and todo list do not support; ``record_rules`` states what counts, and the causes are kept
apart so that the independent re-run clears a stale verification and nothing else. Which bash commands count as
verification is decided by ``verification``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from myrm_agent_harness.agent.middlewares.completion.completion_guard.checklist.record_rules import (
    code_changed_since_proof,
    failed_verification_types,
    is_proof,
    unresolved_failures,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    ToolGroup,
    get_tool_group,
)

logger = logging.getLogger(__name__)


class CriticalCause(StrEnum):
    """Why a run's work is not ready to hand in."""

    UNVERIFIED_CODE = "unverified_code"
    FAILED_VERIFICATION = "failed_verification"
    EMPTY_VERIFICATION = "empty_verification"
    STALE_VERIFICATION = "stale_verification"
    UNRESOLVED_FAILURE = "unresolved_failure"
    INCOMPLETE_TODOS = "incomplete_todos"


VERIFICATION_CAUSES: frozenset[CriticalCause] = frozenset(
    {
        CriticalCause.UNVERIFIED_CODE,
        CriticalCause.FAILED_VERIFICATION,
        CriticalCause.EMPTY_VERIFICATION,
        CriticalCause.STALE_VERIFICATION,
    }
)


@dataclass(frozen=True, slots=True)
class Checklist:
    """The checklist the model reads, and the causes that make the run's work critical."""

    text: str
    causes: frozenset[CriticalCause]

    @property
    def critical(self) -> bool:
        return bool(self.causes)


def find_last_successful_verification_command(records: list[CallRecord]) -> str | None:
    """Extract the bash command string from the most recent successful verification.

    Returns None if no successful verification exists. Used by CompletionGuard
    to independently re-run the verification command in the sandbox.
    """
    for rec in reversed(records):
        if is_proof(rec):
            return str(rec.args.get("command", "")).strip() or None
    return None


def _verification_item(
    records: list[CallRecord],
    verifications: list[CallRecord],
    write_tools: set[str],
) -> tuple[str, CriticalCause | None]:
    """The checklist line for what the run's writes were verified by, and the cause when that is not enough."""
    if not verifications:
        if code_changed_since_proof(records):
            return (
                f"CRITICAL: Code files were modified ({', '.join(sorted(write_tools))}) but NO verification "
                "(tests, lint, type-check) was executed. You MUST run relevant checks before finishing.",
                CriticalCause.UNVERIFIED_CODE,
            )
        return (
            f" Files were modified ({', '.join(sorted(write_tools))}) but NO verification was executed. "
            "If these are text/data files, please manually confirm they meet the requirements.",
            None,
        )
    if failed := failed_verification_types(records):
        return (
            f"CRITICAL: Verification failed for: {', '.join(sorted(category.value for category in failed))}. "
            "You MUST fix failing checks before finishing.",
            CriticalCause.FAILED_VERIFICATION,
        )
    if all(r.success_level == SuccessLevel.EMPTY_OK for r in verifications):
        trivial_types = {r.verification_type.value for r in verifications if r.verification_type}
        return (
            f"CRITICAL: Verification ({', '.join(sorted(trivial_types))}) ran but produced "
            "no meaningful results (0 tests executed / all skipped). "
            "You MUST ensure tests actually run before finishing.",
            CriticalCause.EMPTY_VERIFICATION,
        )
    if code_changed_since_proof(records):
        return (
            "CRITICAL: Code files were modified AFTER the last successful verification. "
            "You MUST re-run tests/lint/type-check to verify the latest changes.",
            CriticalCause.STALE_VERIFICATION,
        )
    verified_types = {r.verification_type.value for r in verifications if r.verification_type and is_proof(r)}
    return (
        f"File modifications ({', '.join(sorted(write_tools))}) verified via "
        f"{', '.join(sorted(verified_types))} — confirm results match expectations.",
        None,
    )


_FRONTEND_RENDER_EXTS: tuple[str, ...] = (
    ".tsx",
    ".jsx",
    ".vue",
    ".svelte",
    ".astro",
    ".css",
    ".scss",
    ".less",
    ".html",
)
_NON_RENDER_PATH_SEGMENTS: frozenset[str] = frozenset(
    {
        "test",
        "tests",
        "spec",
        "specs",
        "__tests__",
        "__test__",
        "store",
        "stores",
        "service",
        "services",
        "util",
        "utils",
        "hook",
        "hooks",
        "api",
        "types",
        "constants",
        "schemas",
        "mocks",
        "mock",
    }
)
_NON_RENDER_FILENAME_PATTERNS: tuple[str, ...] = (".test.", ".spec.", ".d.ts", ".config.", ".stories.")


def _is_non_render_path(path: str) -> bool:
    if set(path.replace("\\", "/").split("/")) & _NON_RENDER_PATH_SEGMENTS:
        return True
    filename = path.rsplit("/", 1)[-1]
    return any(pattern in filename for pattern in _NON_RENDER_FILENAME_PATTERNS)


def _wrote_frontend_render_files(writes: list[CallRecord]) -> bool:
    """Whether a write went to a file a browser would render (not a test, store, config or type file)."""
    paths = (str(record.args.get("path", "")).lower() for record in writes)
    return any(path.endswith(_FRONTEND_RENDER_EXTS) and not _is_non_render_path(path) for path in paths if path)


def _failure_items(records: list[CallRecord], execute_tools: set[str], has_writes: bool) -> tuple[list[str], bool]:
    """The checklist lines for failed calls, and whether a failure that still stands makes the work critical.

    A run that wrote something is held to the failures standing after its last write; a run that wrote nothing
    only gets the whole list as a warning.
    """
    failures = (
        unresolved_failures(records)
        if has_writes
        else [record for record in records if record.success_level == SuccessLevel.FAILURE]
    )
    exec_failures = [record for record in failures if get_tool_group(record.tool_name) == ToolGroup.EXECUTE]
    other_failures = [record for record in failures if get_tool_group(record.tool_name) != ToolGroup.EXECUTE]

    items: list[str] = []
    if execute_tools:
        tools = ", ".join(sorted(execute_tools))
        item = f"Verify execution results from {tools} match expectations."
        if exec_failures:
            if has_writes:
                item = f"CRITICAL: {len(exec_failures)} execution(s) failed in {tools}. You MUST resolve them."
            else:
                item = f"WARNING: {len(exec_failures)} execution(s) had failures in {tools}. Review if they affect the answer."
        items.append(item)

    if other_failures:
        tools = ", ".join(sorted({record.tool_name for record in other_failures}))
        if has_writes:
            items.append(f"CRITICAL: Address {len(other_failures)} unresolved failure(s) in: {tools}.")
        else:
            items.append(f"WARNING: {len(other_failures)} failure(s) in {tools}. Review if they affect the answer.")
    return items, has_writes and bool(failures)


def _todo_lines(workspace_root: str | None, has_writes: bool) -> tuple[list[str], bool]:
    """The checklist lines for unfinished todos, and whether they make the work critical (only after a write)."""
    lines: list[str] = []
    critical = False
    if not workspace_root:
        return lines, critical
    try:
        from myrm_agent_harness.agent.meta_tools.progress.storage import read_todos_sync_from_workspace

        store = read_todos_sync_from_workspace(workspace_root)
        incomplete = store.incomplete_todos() if store else []
        if not incomplete:
            return lines, critical
        blocked_items = [todo for todo in incomplete if todo.status.value == "blocked"]
        actionable_items = [todo for todo in incomplete if todo.status.value != "blocked"]

        if has_writes:
            critical = True
            lines.append("  CRITICAL: You have incomplete todos in your task list!")
        else:
            lines.append("  WARNING: You have incomplete todos in your task list.")
        for todo in incomplete:
            lines.append(f" - Todo {todo.id}: {todo.content} (Status: {todo.status.value})")
        if has_writes:
            if actionable_items:
                lines.append(" You MUST complete actionable todos and call `todo_write(merge=true)` before finishing.")
            if blocked_items:
                lines.append(
                    " For blocked todos that cannot be completed due to external constraints, mark them as 'cancelled' with `todo_write(merge=true)` and explain reasons to user."
                )
        else:
            lines.append(" Review if remaining todos are still needed for your answer.")
        lines.append("")
    except Exception as e:
        logger.warning("[CompletionGuard] Failed to load todos for checklist: %s", e)
    return lines, critical


def assess_checklist(records: list[CallRecord], workspace_root: str | None = None) -> Checklist:
    """Generate a verification checklist from LoopGuard CallRecords, with the causes that make the work critical.

    Groups tool calls by semantic category and produces targeted
    verification items based on what the Agent actually did.

    Internal tool records (``_``-prefixed) are filtered out first. Work is critical only when the run wrote
    something its verification, unresolved failures or todo list do not support (see ``record_rules``); without
    writes every finding is a WARNING.
    """
    records = [r for r in records if not r.tool_name.startswith("_")]

    groups: dict[ToolGroup, list[CallRecord]] = {}
    for rec in records:
        groups.setdefault(get_tool_group(rec.tool_name), []).append(rec)

    writes = groups.get(ToolGroup.WRITE, [])
    has_writes = bool(writes)
    items: list[str] = []
    causes: set[CriticalCause] = set()

    if has_writes:
        verifications = [r for r in records if r.verification_type is not None]
        item, cause = _verification_item(records, verifications, {r.tool_name for r in writes})
        items.append(item)
        if cause is not None:
            causes.add(cause)

    if ToolGroup.BROWSER in groups:
        browser_tools = {r.tool_name for r in groups[ToolGroup.BROWSER]}
        items.append(
            f"Verify browser interactions ({', '.join(sorted(browser_tools))}) "
            "produced expected results — take a snapshot to confirm page state."
        )
    elif has_writes and _wrote_frontend_render_files(writes):
        items.append(
            "WARNING: Frontend rendering files were modified but NO browser "
            "verification was performed. Consider using browser tools to "
            "visually confirm the changes render correctly."
        )

    failure_items, failure_critical = _failure_items(
        records, {r.tool_name for r in groups.get(ToolGroup.EXECUTE, [])}, has_writes
    )
    items.extend(failure_items)
    if failure_critical:
        causes.add(CriticalCause.UNRESOLVED_FAILURE)

    if not items:
        items.append("Confirm the response fully addresses the user's request.")

    lines = ["Before providing your final answer, verify the following:"]
    todo_lines, todos_critical = _todo_lines(workspace_root, has_writes)
    lines.extend(todo_lines)
    if todos_critical:
        causes.add(CriticalCause.INCOMPLETE_TODOS)

    for i, item in enumerate(items, 1):
        lines.append(f" {i}. {item}")
    lines.append("")
    lines.append("RULES:")
    lines.append('- "Looks correct" is NOT verification — run the actual check.')
    lines.append("- Tests you wrote need independent verification — confirm they catch real bugs.")
    lines.append('- "Should work" is NOT "verified" — execute and confirm.')
    lines.append("- If you cannot verify something, state what and why explicitly.")
    lines.append("")

    if causes:
        lines.append(" STATUS: REJECTED. You have CRITICAL errors. You CANNOT finish the task until they are resolved.")
    else:
        lines.append(
            " STATUS: WARNINGS ONLY. If all checks pass, provide your final answer. If issues found, fix them first."
        )

    return Checklist(text="\n".join(lines), causes=frozenset(causes))


def build_checklist(records: list[CallRecord], workspace_root: str | None = None) -> tuple[str, bool]:
    """The checklist text and whether it holds critical errors (see ``assess_checklist``)."""
    checklist = assess_checklist(records, workspace_root=workspace_root)
    return checklist.text, checklist.critical


__all__ = [
    "VERIFICATION_CAUSES",
    "Checklist",
    "CriticalCause",
    "assess_checklist",
    "build_checklist",
    "find_last_successful_verification_command",
]
