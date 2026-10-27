"""What a run's tool records say about its work: which writes went through, what was proven after them, what failed.

Every rule reads the records in call order and nothing else, so each is cheap to state and to test.

[INPUT]
- agent.security.guards.loop_guard::CallRecord, SuccessLevel, ToolGroup, VerificationCategory, get_tool_group (POS: one recorded tool call and its classification)

[OUTPUT]
- is_code_file(): whether a written path is source code the guard asks verification for
- is_proof(): a verification that ran and said something
- code_changed_since_proof(): the last successful code write has no meaningful passing verification after it
- failed_verification_types(): verification categories whose latest run failed
- unresolved_failures(): failures after the last successful write that no later identical call put right

[POS]
The rule layer of the verification checklist. ``checklist`` turns these facts into the text and the verdict the
guard acts on; a failure that came before the work it was exploring for, or that a retry already put right, does not
hold an answer back.
"""

from __future__ import annotations

from collections.abc import Sequence

from myrm_agent_harness.agent.security.guards.loop_guard import (
    CallRecord,
    SuccessLevel,
    ToolGroup,
    VerificationCategory,
    get_tool_group,
)

CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".js",
        ".ts",
        ".jsx",
        ".tsx",
        ".rs",
        ".go",
        ".java",
        ".cpp",
        ".c",
        ".h",
        ".hpp",
        ".cs",
        ".php",
        ".rb",
        ".swift",
    }
)


def is_code_file(path: str) -> bool:
    """Whether ``path`` names a source file the guard asks verification for."""
    return any(path.lower().endswith(ext) for ext in CODE_EXTENSIONS)


def is_proof(record: CallRecord) -> bool:
    """A verification that ran and said something: it did not fail and did not come back empty."""
    return record.verification_type is not None and record.success_level not in (
        SuccessLevel.FAILURE,
        SuccessLevel.EMPTY_OK,
    )


def _last_write_index(records: Sequence[CallRecord], *, code_only: bool) -> int:
    """Index of the last write that went through (a code file only with ``code_only``); -1 when there is none."""
    for index in range(len(records) - 1, -1, -1):
        record = records[index]
        if get_tool_group(record.tool_name) != ToolGroup.WRITE or record.success_level == SuccessLevel.FAILURE:
            continue
        if not code_only or is_code_file(str(record.args.get("path", ""))):
            return index
    return -1


def code_changed_since_proof(records: Sequence[CallRecord]) -> bool:
    """Code was written, and nothing after the last such write proved it works."""
    last_code_write = _last_write_index(records, code_only=True)
    return last_code_write >= 0 and not any(is_proof(record) for record in records[last_code_write + 1 :])


def failed_verification_types(records: Sequence[CallRecord]) -> frozenset[VerificationCategory]:
    """Verification categories whose latest run failed; a later run of the same category that passed puts it right."""
    latest: dict[VerificationCategory, SuccessLevel | None] = {}
    for record in records:
        if record.verification_type is not None:
            latest[record.verification_type] = record.success_level
    return frozenset(category for category, level in latest.items() if level == SuccessLevel.FAILURE)


def unresolved_failures(records: Sequence[CallRecord]) -> list[CallRecord]:
    """Failures that still stand: after the last successful write, and not followed by the same call succeeding.

    Anything earlier was explored before the work was done, so the work superseded it. A verification
    failure is judged by ``failed_verification_types``, not here.
    """
    boundary = _last_write_index(records, code_only=False)
    unresolved: list[CallRecord] = []
    succeeded_later: set[tuple[str, str]] = set()
    for index in range(len(records) - 1, boundary, -1):
        record = records[index]
        call = (record.tool_name, record.args_hash)
        if record.success_level != SuccessLevel.FAILURE:
            succeeded_later.add(call)
        elif record.verification_type is None and call not in succeeded_later:
            unresolved.append(record)
    unresolved.reverse()
    return unresolved


__all__ = [
    "CODE_EXTENSIONS",
    "code_changed_since_proof",
    "failed_verification_types",
    "is_code_file",
    "is_proof",
    "unresolved_failures",
]
