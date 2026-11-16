"""A tool factory that takes a description locale is given one at every place production code calls it.

[INPUT]
- myrm_agent_harness and app/**/*.py: ``create_*`` functions with a ``locale`` or ``description_locale`` parameter, and
  every call of them

[OUTPUT]
- Fails when a call leaves the locale out or passes a literal ``None``: the tool then shows the model its English
  description whatever language the session speaks. ``**options`` counts as passing it.
- Fails when a registered call is gone or passes the locale now: its entry has to go.

[POS]
tests/architecture/test_tool_description_locale_wiring.py - the harness keeps a Chinese and an English description for
many tools and picks one by the ``locale`` the caller passes. The tests of each factory pass their own locale, so none of
them sees a production call that passes nothing; this guard does. It matches calls by name: a factory imported under
another name, bound to a variable first or reached through ``getattr`` is not seen, and only that the keyword is passed is
checked, not that its value is the session's.
"""

from __future__ import annotations

import ast
from collections.abc import Mapping
from functools import cache
from pathlib import Path

import myrm_agent_harness

_ROOTS = {
    "harness": Path(myrm_agent_harness.__file__).resolve().parent,
    "server": Path(__file__).resolve().parents[2] / "app",
}
_LOCALE_PARAMETERS = frozenset({"locale", "description_locale"})
# 21 factories exist today; a scan that finds far fewer has gone blind (the prefix renamed, a root moved).
_MIN_FACTORIES = 15

# Calls that leave the locale out on purpose. Key: "<root>:<path inside the root>::<factory>".
_EXEMPT = {
    "harness:agent/meta_tools/answer_user_tool.py::create_answer_user_tool": (
        "module-level instance for direct importers; get_meta_tools builds the session's instance with the locale"
    ),
    "harness:agent/middlewares/context_pipeline/context_pipeline_middleware.py::create_file_read_tool": (
        "fallback tool that the registry priority hides unless the built-in tools are switched off"
    ),
    "server:api/background_tasks/test_fixtures.py::create_bash_code_execute_tool": "developer fixture, English by design",
    "server:api/mcp/endpoint.py::create_wiki_agent_tools": "an MCP client has no session language",
}
# Calls that still leave it out and are to be fixed. An entry fails as stale as soon as its call passes the locale.
_KNOWN_GAPS = {
    "server:ai_agents/general_agent/factory/builder.py::create_goal_tools": "the goal tool does not get the session language yet",
    "server:ai_agents/general_agent/tool_setup/cron.py::create_cron_tools": (
        "the cron description gets the session language together with the rewrite of its Chinese text"
    ),
    "server:ai_agents/general_agent/tool_setup/skill.py::create_skill_manage_tool": "not wired yet",
    "server:ai_agents/general_agent/tool_setup/skill.py::create_skill_market_tool": "not wired yet",
}
_REGISTERED = frozenset(_EXEMPT) | frozenset(_KNOWN_GAPS)


def _callee(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    return call.func.attr if isinstance(call.func, ast.Attribute) else None


def _passes_locale(call: ast.Call, parameters: frozenset[str]) -> bool:
    return any(
        keyword.arg is None  # ``**options`` cannot be judged
        or (keyword.arg in parameters and not (isinstance(keyword.value, ast.Constant) and keyword.value.value is None))
        for keyword in call.keywords
    )


def calls_without_locale(source: str, factories: Mapping[str, frozenset[str]]) -> list[tuple[int, str]]:
    """``(line, factory)`` of each call of a factory that does not pass its locale."""
    return [
        (node.lineno, name)
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.Call) and (name := _callee(node)) in factories and not _passes_locale(node, factories[name])
    ]


@cache
def _sources() -> tuple[tuple[str, str, str], ...]:
    """``(root, path inside the root, source)`` of each Python file outside the tests that mentions a ``create_`` name."""
    sources: list[tuple[str, str, str]] = []
    for label, root in _ROOTS.items():
        for path in sorted(root.rglob("*.py")):
            relative = path.relative_to(root)
            source = path.read_text(encoding="utf-8")
            if "tests" not in relative.parts and "create_" in source:
                sources.append((label, relative.as_posix(), source))
    return tuple(sources)


@cache
def _factories() -> dict[str, frozenset[str]]:
    """Each ``create_*`` function with a locale parameter, and the locale parameter names its definitions have."""
    found: dict[str, set[str]] = {}
    for _, _, source in _sources():
        if "def create_" not in source:
            continue
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("create_"):
                parameters = {argument.arg for argument in (*node.args.args, *node.args.kwonlyargs)} & _LOCALE_PARAMETERS
                if parameters:
                    found.setdefault(node.name, set()).update(parameters)
    return {name: frozenset(parameters) for name, parameters in found.items()}


@cache
def _calls_without_locale() -> dict[str, list[int]]:
    """Registry key -> lines of the calls in that file that leave the factory's locale out."""
    missing: dict[str, list[int]] = {}
    factories = _factories()
    for label, relative, source in _sources():
        if any(name in source for name in factories):
            for line, factory in calls_without_locale(source, factories):
                missing.setdefault(f"{label}:{relative}::{factory}", []).append(line)
    return missing


def test_a_call_that_leaves_the_locale_out_is_found() -> None:
    factories = {"create_tool": frozenset({"locale"})}

    assert calls_without_locale("create_tool(a)\nmodule.create_tool(a, b=1)", factories) == [
        (1, "create_tool"),
        (2, "create_tool"),
    ]
    assert calls_without_locale("create_tool(a, locale=None)", factories) == [(1, "create_tool")]


def test_a_passed_locale_a_splat_and_unrelated_calls_are_accepted() -> None:
    factories = {"create_tool": frozenset({"locale"})}
    source = "create_tool(a, locale=loc)\ncreate_tool(a, **options)\nother(a)\ncreate_tool_x(a)\nmodule.create_tool_y(a)"

    assert calls_without_locale(source, factories) == []


def test_the_scan_sees_the_known_factories() -> None:
    assert len(_factories()) >= _MIN_FACTORIES, (
        "the source scan found fewer locale-aware factories than exist; the guard is blind"
    )


def test_every_registered_call_still_leaves_the_locale_out() -> None:
    stale = sorted(_REGISTERED - set(_calls_without_locale()))

    assert not stale, f"these calls pass a locale now or are gone; drop their entries: {stale}"


def test_every_call_passes_the_session_locale() -> None:
    offenders = [
        f"{key} (line {', '.join(map(str, lines))})"
        for key, lines in sorted(_calls_without_locale().items())
        if key not in _REGISTERED
    ]

    assert not offenders, (
        "these tool factories take a description locale, and the call passes none, so the model sees the English "
        "description in every session: pass the session's locale, or register the call with the reason it needs none:\n"
        + "\n".join(offenders)
    )
