"""A memory router mounted for every user must be registered: new ones sit behind MYRM_MEMORY_LABS or name a real caller.

[POS]
tests/architecture/test_memory_router_mounts.py

[INPUT]
- app/api/memory/router.py: parsed, never imported (importing it mounts every router)
- data/memory_default_mounts.txt: one default mount per line, `<include_router first argument>` for an unattributed
  mount (shrink-only) or `<argument> | <caller file:line>` for a mount that names its default-visible caller

[OUTPUT]
- Fails when `router.py` mounts a router unconditionally and the file does not list it
- Fails when a listed mount is gone, so the file can only shrink
- Fails when an admitted entry names no caller, or a caller that is not a real line of an existing non-test file

A mount under `if` (the MYRM_MEMORY_LABS gate, the local-mode fixtures) is conditional and is not listed. The route
consumer gate cannot stand in for this one: a service file that only a hidden panel imports still counts as a caller
there, so an in-process engine with demo data and no persistence passes it. An unconditional mount puts the routes in
every user's API, so it has to name the caller that makes it a product feature; everything else belongs behind the gate.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

_SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
_ROUTER_FILE = _SERVER_ROOT / "app" / "api" / "memory" / "router.py"
_MOUNTS_FILE = Path(__file__).resolve().parent / "data" / "memory_default_mounts.txt"
_MONOREPO_ROOT = _SERVER_ROOT.parents[1]
_EVIDENCE_RE = re.compile(r"^(?P<path>[^:\s]+):(?P<first>\d+)(?:-(?P<last>\d+))?$")
_TEST_PATH_PARTS = frozenset({"tests", "test", "__tests__"})


def default_mounts(source: str) -> list[str]:
    """First argument of every module-level `router.include_router(...)` statement, in source order."""
    mounts: list[str] = []
    for node in ast.parse(source).body:
        if not (isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)):
            continue
        call = node.value
        func = call.func
        is_mount = (
            isinstance(func, ast.Attribute)
            and func.attr == "include_router"
            and isinstance(func.value, ast.Name)
            and func.value.id == "router"
        )
        if is_mount and call.args:
            mounts.append(ast.unparse(call.args[0]))
    return mounts


def read_entries(text: str) -> dict[str, str | None]:
    """`mount` or `mount | evidence` per line -> {mount: evidence or None}; blank lines and `#` comments are skipped."""
    entries: dict[str, str | None] = {}
    for line in text.splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        mount, separator, evidence = line.partition(" | ")
        entries[mount.strip()] = evidence.strip() if separator else None
    return entries


def unverifiable_callers(entries: dict[str, str | None], root: Path) -> list[str]:
    """Admitted entries whose `file:line` is not a real line of an existing non-test file under `root`."""
    problems: list[str] = []
    for mount, evidence in entries.items():
        if not evidence:
            continue
        match = _EVIDENCE_RE.match(evidence)
        if match is None:
            problems.append(f"{mount}: `{evidence}` is not `file:line`")
            continue
        relative = Path(match["path"])
        path = root / relative
        if _TEST_PATH_PARTS & set(relative.parts):
            problems.append(f"{mount}: {relative} is test code, not a product caller")
        elif not path.is_file():
            problems.append(f"{mount}: {relative} does not exist")
        else:
            last = int(match["last"] or match["first"])
            if last > len(path.read_text(encoding="utf-8").splitlines()):
                problems.append(f"{mount}: {relative} has no line {last}")
    return problems


@pytest.fixture(scope="module")
def mounted() -> set[str]:
    return set(default_mounts(_ROUTER_FILE.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def entries() -> dict[str, str | None]:
    return read_entries(_MOUNTS_FILE.read_text(encoding="utf-8"))


@pytest.mark.architecture
def test_default_mounts_are_registered(mounted: set[str], entries: dict[str, str | None]) -> None:
    unregistered = sorted(mounted - entries.keys())
    assert not unregistered, (
        "memory routers mounted for every user but not registered. Mount them under `if settings.memory_labs_enabled:` "
        "in app/api/memory/router.py, or add `<mount> | <caller file:line>` to "
        "tests/architecture/data/memory_default_mounts.txt naming the default-visible caller:\n" + "\n".join(unregistered)
    )


@pytest.mark.architecture
def test_registered_mounts_are_current(mounted: set[str], entries: dict[str, str | None]) -> None:
    gone = sorted(entries.keys() - mounted)
    assert not gone, f"no longer mounted unconditionally, remove from memory_default_mounts.txt: {gone}"


@pytest.mark.architecture
def test_admitted_mounts_name_a_caller(entries: dict[str, str | None]) -> None:
    blank = sorted(mount for mount, evidence in entries.items() if evidence == "")
    assert not blank, f"an admitted mount needs `mount | caller file:line`: {blank}"


@pytest.mark.architecture
def test_admitted_mount_callers_exist(entries: dict[str, str | None]) -> None:
    problems = unverifiable_callers(entries, _MONOREPO_ROOT)
    assert not problems, "admitted memory mounts must cite a real product caller:\n" + "\n".join(problems)


_SAMPLE = """
router.include_router(pending.router, tags=["a"])
if settings.memory_labs_enabled:
    router.include_router(command_center.router, tags=["b"])
router.include_router(
    profile_notes_router,
    tags=["c"],
)
other.include_router(unrelated_router)
helper(router.include_router)
"""


def test_default_mounts_ignores_conditional_and_foreign_includes() -> None:
    assert default_mounts(_SAMPLE) == ["pending.router", "profile_notes_router"]


def test_read_entries_distinguishes_bare_admitted_and_blank_evidence() -> None:
    parsed = read_entries("# header\n\nbare_router\nadmitted_router | web/Chat.tsx:10\nblank_router | \n")
    assert parsed == {"bare_router": None, "admitted_router": "web/Chat.tsx:10", "blank_router": ""}


def test_unverifiable_callers_reports_missing_test_malformed_and_out_of_range_evidence(tmp_path: Path) -> None:
    (tmp_path / "web").mkdir()
    (tmp_path / "web" / "Chat.tsx").write_text("one\ntwo\nthree\n", encoding="utf-8")
    entries: dict[str, str | None] = {
        "bare_router": None,
        "ok_router": "web/Chat.tsx:3",
        "range_router": "web/Chat.tsx:1-2",
        "missing_router": "web/Gone.tsx:1",
        "line_router": "web/Chat.tsx:4",
        "test_router": "web/__tests__/Chat.test.tsx:1",
        "malformed_router": "Chat.tsx",
    }

    problems = unverifiable_callers(entries, tmp_path)

    assert [problem.partition(":")[0] for problem in problems] == [
        "missing_router",
        "line_router",
        "test_router",
        "malformed_router",
    ]


def test_new_unconditional_mount_without_registration_is_reported() -> None:
    source = 'router.include_router(orphan_lab_router, tags=["x"])\n'

    assert set(default_mounts(source)) - read_entries("pending.router\n").keys() == {"orphan_lab_router"}
