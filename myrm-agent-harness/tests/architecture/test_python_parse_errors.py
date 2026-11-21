"""Architecture guard: a handler around a Python parse call covers every failure the text can cause.

``ast.parse``, ``compile`` and ``ast.literal_eval`` run on text nobody here wrote, and a handler that names only
``SyntaxError`` lets the parser's other failures (a lone surrogate, an expression chained past the stack, a literal
Python cannot build) escape as a crash that the author of the text chose. ``utils.python_parse`` holds the one
definition of those failures; this test refuses a handler that names ``SyntaxError`` around a parse call without
covering the rest of that set.
"""

from __future__ import annotations

import ast
import builtins
from pathlib import Path

import pytest

from myrm_agent_harness.utils.python_parse import PYTHON_LITERAL_ERRORS, PYTHON_PARSE_ERRORS

_HARNESS_SRC = Path(__file__).resolve().parent.parent.parent / "src" / "myrm_agent_harness"
_CONSTANTS = {"PYTHON_PARSE_ERRORS": PYTHON_PARSE_ERRORS, "PYTHON_LITERAL_ERRORS": PYTHON_LITERAL_ERRORS}


def _parse_call_kind(call: ast.Call) -> str | None:
    """``"literal"`` for ``ast.literal_eval``, ``"parse"`` for ``ast.parse`` and ``compile``, else ``None``."""
    func = call.func
    if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name) and func.value.id == "ast":
        return {"parse": "parse", "literal_eval": "literal"}.get(func.attr)
    if isinstance(func, ast.Name):
        return {"compile": "parse", "literal_eval": "literal"}.get(func.id)
    return None


def _handler_classes(handler: ast.ExceptHandler) -> tuple[type[BaseException], ...]:
    """The exception classes one handler catches; a name this guard cannot resolve covers nothing."""
    if handler.type is None:
        return (BaseException,)
    caught: list[type[BaseException]] = []
    pending: list[ast.expr] = [handler.type]
    while pending:
        node = pending.pop()
        if isinstance(node, ast.Tuple):
            pending.extend(node.elts)
        elif isinstance(node, ast.Starred):
            pending.append(node.value)
        elif isinstance(node, ast.Name | ast.Attribute):
            name = node.id if isinstance(node, ast.Name) else node.attr
            if name in _CONSTANTS:
                caught.extend(_CONSTANTS[name])
            elif isinstance(builtin := getattr(builtins, name, None), type) and issubclass(builtin, BaseException):
                caught.append(builtin)
    return tuple(caught)


def _partial_parse_handlers(source: str) -> list[int]:
    """Lines of ``try`` statements that name ``SyntaxError`` around a parse call yet leave a parser failure uncaught."""
    offenders: list[int] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Try):
            continue
        kinds = {
            kind
            for statement in node.body
            for call in ast.walk(statement)
            if isinstance(call, ast.Call) and (kind := _parse_call_kind(call))
        }
        if not kinds:
            continue
        caught = [cls for handler in node.handlers for cls in _handler_classes(handler)]
        if not any(issubclass(cls, SyntaxError) for cls in caught):
            continue
        required = PYTHON_LITERAL_ERRORS if "literal" in kinds else PYTHON_PARSE_ERRORS
        if not all(any(issubclass(failure, cls) for cls in caught) for failure in required):
            offenders.append(node.lineno)
    return offenders


@pytest.mark.architecture
def test_no_handler_names_syntax_error_without_the_rest_of_the_parser_failures() -> None:
    offenders = {
        py_file.relative_to(_HARNESS_SRC).as_posix(): lines
        for py_file in sorted(_HARNESS_SRC.rglob("*.py"))
        if (lines := _partial_parse_handlers(py_file.read_text(encoding="utf-8")))
    }

    assert not offenders, (
        "A handler around ast.parse / compile / ast.literal_eval names SyntaxError but not every failure the parser "
        f"can raise for text it is given; catch utils.python_parse.PYTHON_PARSE_ERRORS (or PYTHON_LITERAL_ERRORS): "
        f"{offenders}"
    )


@pytest.mark.parametrize(
    "source",
    [
        "try:\n    ast.parse(text)\nexcept SyntaxError:\n    pass\n",
        "try:\n    compile(text, 'f', 'exec')\nexcept (SyntaxError, ValueError):\n    pass\n",
        "try:\n    tree = ast.parse(text)\nexcept (SyntaxError, ValueError, RecursionError):\n    pass\n",
        "try:\n    ast.literal_eval(text)\nexcept PYTHON_PARSE_ERRORS:\n    pass\n",
        "try:\n    ast.literal_eval(text)\nexcept (SyntaxError, ValueError, MemoryError, RecursionError):\n    pass\n",
        "try:\n    ast.parse(text)\nexcept SyntaxError:\n    pass\nexcept ValueError:\n    pass\n",
    ],
    ids=[
        "syntax-error-only",
        "no-stack-failures",
        "no-memory-error",
        "literal-without-type-error",
        "literal-spelled-out-without-type-error",
        "several-handlers-still-partial",
    ],
)
def test_guard_flags_a_partial_handler(source: str) -> None:
    assert _partial_parse_handlers(source) == [1]


@pytest.mark.parametrize(
    "source",
    [
        "try:\n    ast.parse(text)\nexcept PYTHON_PARSE_ERRORS:\n    pass\n",
        "try:\n    ast.parse(text)\nexcept (SyntaxError, *PYTHON_PARSE_ERRORS):\n    pass\n",
        "try:\n    ast.parse(text)\nexcept SyntaxError:\n    pass\nexcept PYTHON_PARSE_ERRORS:\n    pass\n",
        "try:\n    ast.parse(text)\nexcept (SyntaxError, ValueError, MemoryError, RecursionError):\n    pass\n",
        "try:\n    ast.literal_eval(text)\nexcept PYTHON_LITERAL_ERRORS:\n    pass\n",
        "try:\n    ast.parse(text)\nexcept Exception:\n    pass\n",
        "try:\n    ast.parse(text)\nexcept:\n    pass\n",
        "try:\n    ast.parse(text)\nexcept KeyError:\n    pass\n",
        "try:\n    json.loads(text)\nexcept SyntaxError:\n    pass\n",
    ],
    ids=[
        "constant",
        "starred-constant",
        "constant-in-a-later-handler",
        "spelled-out-in-full",
        "literal-constant",
        "exception",
        "bare",
        "handler-is-not-about-syntax",
        "not-a-parse-call",
    ],
)
def test_guard_accepts_a_complete_handler_and_ignores_unrelated_code(source: str) -> None:
    assert _partial_parse_handlers(source) == []
