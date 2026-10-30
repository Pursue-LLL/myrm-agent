"""An event the server writes past ``EventLogger`` carries nothing the logger would have redacted.

[INPUT]
- app/**/*.py: every call that builds a ``StructuredEvent`` (the record a backend appends)

[OUTPUT]
- Fails when a server module builds a ``StructuredEvent`` and is not listed below, when a listed module that writes
  free text does not call ``sanitize_event_data``, or when a listed module no longer builds one (so the list cannot rot).

[POS]
tests/architecture/test_event_writers_redact.py — ``EventLogger.log`` redacts every payload it writes; a module that
appends to a backend directly skips that step, and the log is read back by the audit pull, the support bundle and the
evolution pipeline.
"""

from __future__ import annotations

import ast
from pathlib import Path

_APP = Path(__file__).resolve().parents[2] / "app"
_BUILDER = "StructuredEvent"
_REDACTOR = "sanitize_event_data"

# Module -> (why it builds an event itself, whether its payload carries text that needs the redaction).
_DIRECT_WRITERS: dict[str, tuple[str, bool]] = {
    "api/webui/vnc_routes.py": ("takeover trace of the page state a person left behind (URLs, accessibility tree)", True),
    "services/chat/conversation_fork_manager.py": ("fork point: chat ids and an index, no free text", False),
}


def _called_names(source: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call):
            func = node.func
            names.add(func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else "")
    return names


def _sources_that_build_events() -> dict[str, str]:
    sources = {path.relative_to(_APP).as_posix(): path.read_text(encoding="utf-8") for path in sorted(_APP.rglob("*.py"))}
    return {path: source for path, source in sources.items() if _BUILDER in _called_names(source)}


def test_a_module_that_builds_an_event_itself_is_listed_with_its_reason() -> None:
    unlisted = sorted(set(_sources_that_build_events()) - set(_DIRECT_WRITERS))

    assert not unlisted, f"append through EventLogger (it redacts), or list the module in _DIRECT_WRITERS with why: {unlisted}"


def test_a_direct_writer_of_free_text_redacts_its_payload() -> None:
    sources = _sources_that_build_events()
    unredacted = [
        path
        for path, (_why, carries_text) in _DIRECT_WRITERS.items()
        if carries_text and _REDACTOR not in _called_names(sources.get(path, ""))
    ]

    assert not unredacted, f"call myrm_agent_harness.api.{_REDACTOR} on the payload before it is written: {unredacted}"


def test_every_listed_writer_still_builds_an_event() -> None:
    stale = sorted(set(_DIRECT_WRITERS) - set(_sources_that_build_events()))

    assert not stale, f"remove these from _DIRECT_WRITERS: {stale}"
