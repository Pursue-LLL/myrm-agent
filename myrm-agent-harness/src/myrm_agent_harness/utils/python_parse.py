"""What the Python parser raises for text that is not a usable program.

``ast.parse``, ``compile`` and ``ast.literal_eval`` run on text nobody here wrote: a model's script, a skill file, a tool
argument, a workflow template. A syntax error is the common failure, but the parser has others, and a handler that names
only ``SyntaxError`` lets them escape. In a gate that crash is a verdict the author of the text chooses: the caller
either fails on every call, or, when an outer handler swallows the error, falls back to a permissive default.

``PYTHON_PARSE_ERRORS`` names every failure the text itself can cause:

- ``SyntaxError`` (and ``IndentationError``): the text is not Python.
- ``ValueError``: the parser cannot take the text at all; a lone surrogate raises its subclass ``UnicodeEncodeError``.
- ``RecursionError``: an expression chained or nested so deeply that building the tree, or a recursive walk over it,
  exceeds the interpreter's recursion limit. A visitor that recurses once per level gives up after a few hundred
  chained operators, far below any limit of the parser itself.
- ``MemoryError``: the parser's own stack is exhausted by the same kind of text.

``PYTHON_LITERAL_ERRORS`` adds ``TypeError`` for ``ast.literal_eval``, which raises it for a literal the parser accepts
but Python cannot build, such as a dict key or a set member that is a list.

[INPUT]
- (none)

[OUTPUT]
- PYTHON_PARSE_ERRORS: Every exception ``ast.parse``, ``compile`` and a recursive walk of the parsed tree raise for text
  that is not a usable program.
- PYTHON_LITERAL_ERRORS: ``PYTHON_PARSE_ERRORS`` plus ``TypeError``, the failures of ``ast.literal_eval``.

[POS]
The one definition of "this text could not be analysed as Python" for every site that treats such text as a normal
outcome. An architecture test refuses a handler that names ``SyntaxError`` around a parse call without covering the rest
of this set, and a completeness test checks the set against what the running interpreter raises.
"""

from __future__ import annotations

PYTHON_PARSE_ERRORS: tuple[type[Exception], ...] = (SyntaxError, ValueError, RecursionError, MemoryError)
PYTHON_LITERAL_ERRORS: tuple[type[Exception], ...] = (*PYTHON_PARSE_ERRORS, TypeError)
