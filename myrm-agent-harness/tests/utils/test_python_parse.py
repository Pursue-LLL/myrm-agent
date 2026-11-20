"""``PYTHON_PARSE_ERRORS`` and ``PYTHON_LITERAL_ERRORS`` hold what the parser raises for text it cannot take.

Which text overflows the parser's stack depends on the interpreter, so the assertions are the ones that hold on every
interpreter: whatever ``ast.parse``, ``compile`` and ``ast.literal_eval`` raise for the inputs below is in the constant,
and the inputs that fail the same way everywhere (a syntax error, a lone surrogate, an unhashable dict key) do fail.
"""

from __future__ import annotations

import ast
from collections.abc import Callable

import pytest

from myrm_agent_harness.utils.python_parse import PYTHON_LITERAL_ERRORS, PYTHON_PARSE_ERRORS

_PROGRAMS = {
    "lone-surrogate": "x = '\ud800'",
    "null-byte": "x = 1\x00",
    "digits-past-the-int-limit": "x = " + "9" * 5_000,
    "nested-parentheses": "(" * 1_000 + ")" * 1_000,
    "unary-chain": "x = " + "-" * 20_000 + "1",
    "operator-chain": "x = " + " + ".join(["1"] * 30_000),
    "attribute-chain": "x = a" + ".b" * 30_000,
    "call-chain": "x = a" + "()" * 30_000,
    "elif-chain": "if a:\n    pass\n" + "elif a:\n    pass\n" * 30_000,
    "nested-literal": "x = " + "[" * 300 + "]" * 300,
}
_LITERALS = {
    "unhashable-dict-key": "{[1]: 2}",
    "unhashable-set-member": "{[1]}",
    "not-a-literal": "x",
    "lone-surrogate": "'\ud800'",
    "unary-chain": "[" + "-" * 20_000 + "1]",
    "operator-chain": "[" + " + ".join(["1"] * 30_000) + "]",
    "nested-brackets": "[" * 32_000 + "]" * 32_000,
}
_PARSERS: dict[str, Callable[[str], object]] = {
    "ast.parse": ast.parse,
    "compile": lambda text: compile(text, "<test>", "exec"),
}


def _raised(parse: Callable[[str], object], text: str) -> Exception | None:
    try:
        parse(text)
    except Exception as exc:
        return exc
    return None


@pytest.mark.parametrize("parser", _PARSERS.values(), ids=_PARSERS.keys())
@pytest.mark.parametrize("text", _PROGRAMS.values(), ids=_PROGRAMS.keys())
def test_whatever_the_parser_raises_for_a_program_is_in_the_constant(
    parser: Callable[[str], object], text: str
) -> None:
    exc = _raised(parser, text)

    assert exc is None or isinstance(exc, PYTHON_PARSE_ERRORS), f"{type(exc).__name__} escapes PYTHON_PARSE_ERRORS"


@pytest.mark.parametrize("text", _LITERALS.values(), ids=_LITERALS.keys())
def test_whatever_literal_eval_raises_is_in_the_literal_constant(text: str) -> None:
    exc = _raised(ast.literal_eval, text)

    assert exc is None or isinstance(exc, PYTHON_LITERAL_ERRORS), f"{type(exc).__name__} escapes PYTHON_LITERAL_ERRORS"


def test_the_inputs_reach_the_failures_the_constants_name() -> None:
    """A completeness check over inputs that raise nothing would pass for any constant."""
    program_failures = {type(exc) for text in _PROGRAMS.values() if (exc := _raised(ast.parse, text))}
    literal_failures = {type(exc) for text in _LITERALS.values() if (exc := _raised(ast.literal_eval, text))}

    assert any(issubclass(failure, SyntaxError) for failure in program_failures)
    assert any(issubclass(failure, ValueError) for failure in program_failures)
    assert TypeError in literal_failures
