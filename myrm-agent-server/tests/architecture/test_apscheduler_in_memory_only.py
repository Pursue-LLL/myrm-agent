"""APScheduler stays in-process, so the serializers its advisory concerns never read bytes from outside.

[POS]
tests/architecture/test_apscheduler_in_memory_only.py

[INPUT]
- app/**/*.py: every scheduler construction and every apscheduler import
- apscheduler (installed): the data store and event broker of a scheduler built without arguments

[OUTPUT]
- Fails when a scheduler is handed a data store or an event broker, when a persistent data store, a networked
  event broker or a serializer module is imported, or when the default pair stops being in-memory.

GHSA-9cfw-f3f9-7mm7 (CVE-2026-31072, also published as PYSEC-2026-282) covers APScheduler 4.0.0a1 to 4.0.0a6:
its JSON and CBOR serializers rebuild arbitrary classes from the bytes they are given, so bytes that an attacker
can place in a shared database or on a message broker run code. A scheduler built without arguments pairs a
``MemoryDataStore`` with a ``LocalEventBroker``; neither serializes anything, so no foreign bytes reach a serializer.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from apscheduler import AsyncScheduler
from apscheduler.datastores.base import BaseExternalDataStore
from apscheduler.eventbrokers.base import BaseExternalEventBroker

_APP = Path(__file__).resolve().parents[2] / "app"
_SCHEDULER_CLASSES = frozenset({"AsyncScheduler", "Scheduler"})
# The first two constructor parameters are the data store and the event broker, so a positional argument selects them too.
_BACKEND_KEYWORDS = frozenset({"data_store", "event_broker"})
# Persistent data stores, networked event brokers and the serializers they apply live in these subpackages.
_EXTERNAL_MODULES = ("apscheduler.datastores", "apscheduler.eventbrokers", "apscheduler.serializers")


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    return func.attr if isinstance(func, ast.Attribute) else ""


def _scheduler_calls(tree: ast.AST) -> list[ast.Call]:
    return [node for node in ast.walk(tree) if isinstance(node, ast.Call) and _called_name(node) in _SCHEDULER_CLASSES]


def _imported_modules(tree: ast.AST) -> list[tuple[int, str]]:
    """Every module an import statement can bring in, including submodules named by ``from package import name``."""
    modules: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend((node.lineno, alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.append((node.lineno, node.module))
            modules.extend((node.lineno, f"{node.module}.{alias.name}") for alias in node.names)
    return modules


def _violations(source: str) -> list[str]:
    """Name each place where the source gives a scheduler an external backend or imports one."""
    tree = ast.parse(source)
    found: list[str] = []
    for call in _scheduler_calls(tree):
        if call.args:
            found.append(f"line {call.lineno}: scheduler built with positional arguments")
        found.extend(
            f"line {call.lineno}: scheduler built with {keyword.arg or '**options'}"
            for keyword in call.keywords
            if keyword.arg is None or keyword.arg in _BACKEND_KEYWORDS
        )
    found.extend(
        f"line {line}: imports {module}" for line, module in _imported_modules(tree) if module.startswith(_EXTERNAL_MODULES)
    )
    return found


def _apscheduler_sources() -> dict[Path, str]:
    """The server modules that can build a scheduler or import apscheduler; every other module cannot violate the guard."""
    sources = {path: path.read_text(encoding="utf-8") for path in sorted(_APP.rglob("*.py"))}
    return {path: text for path, text in sources.items() if "apscheduler" in text or "AsyncScheduler" in text}


def test_every_server_scheduler_runs_in_memory_only() -> None:
    sources = _apscheduler_sources()

    constructions = sum(len(_scheduler_calls(ast.parse(text))) for text in sources.values())
    assert constructions >= 8, (
        f"expected the known scheduler constructions, found {constructions}: the scan no longer reaches them"
    )
    violations = {
        path.relative_to(_APP.parent).as_posix(): found for path, text in sources.items() if (found := _violations(text))
    }
    assert not violations, f"these modules give APScheduler a persistent store, a networked broker or a serializer: {violations}"


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("AsyncScheduler(data_store=store)", id="data-store-keyword"),
        pytest.param("AsyncScheduler(event_broker=broker)", id="event-broker-keyword"),
        pytest.param("apscheduler.AsyncScheduler(event_broker=broker)", id="attribute-call"),
        pytest.param("AsyncScheduler(store, broker)", id="positional"),
        pytest.param("AsyncScheduler(**options)", id="unpacked-options"),
        pytest.param("from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore", id="sqlalchemy-store"),
        pytest.param("import apscheduler.eventbrokers.redis", id="redis-broker"),
        pytest.param("from apscheduler import serializers", id="serializers-package"),
        pytest.param("from apscheduler.serializers.json import JSONSerializer", id="json-serializer"),
    ],
)
def test_the_detector_flags_an_external_backend(source: str) -> None:
    assert _violations(source)


@pytest.mark.parametrize(
    "source",
    [
        pytest.param("AsyncScheduler()", id="default"),
        pytest.param("AsyncScheduler(identity='worker')", id="other-keyword"),
        pytest.param("from apscheduler import AsyncScheduler", id="scheduler-import"),
        pytest.param("from apscheduler.triggers.cron import CronTrigger", id="trigger-import"),
    ],
)
def test_the_detector_passes_an_in_memory_scheduler(source: str) -> None:
    assert not _violations(source)


def test_a_scheduler_built_without_arguments_keeps_schedules_and_events_in_memory() -> None:
    scheduler = AsyncScheduler()

    assert not isinstance(scheduler.data_store, BaseExternalDataStore)
    assert not isinstance(scheduler.event_broker, BaseExternalEventBroker)
