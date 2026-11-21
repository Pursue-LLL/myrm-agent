"""Code type detector for bash vs Python execution routing.

Detects whether user input is Python or Bash and extracts embedded Python from
``python -c`` commands. Framework-agnostic; consumed by BashExecutor and executors.

[INPUT]
- python_extractor::extract_python_from_bash (POS: quote-aware Python extraction)
- utils.text_utils::unwrap_markdown_fence (POS: text utilities; unwraps one Markdown fence around a command)
- utils.python_parse::PYTHON_PARSE_ERRORS (POS: What the Python parser raises for text that is not a usable program)

[OUTPUT]
- CodeType: Python vs Bash enum
- CodeDetectionResult: detection outcome with extracted code
- CodeTypeDetector: detector class
- code_detector: module singleton
- detect_for_execution: the route of a command as the bash tool takes it, with the Python to run
- runs_as_python: whether the bash tool hands a command to the Python wrapper instead of a shell

[POS]
Pure code analysis with zero agent/ runtime dependencies. Lives in toolkits
alongside python_extractor SSOT. Text that is not a ``python -c`` command or a heredoc wrapper is routed by its
syntax tree: it is Python when it parses and holds something a shell command line cannot be.
"""

from __future__ import annotations

import ast
import re
import warnings
from dataclasses import dataclass
from enum import StrEnum

from myrm_agent_harness.toolkits.code_execution.python_extractor import (
    extract_python_from_bash,
)
from myrm_agent_harness.utils.python_parse import PYTHON_PARSE_ERRORS
from myrm_agent_harness.utils.text_utils import unwrap_markdown_fence

# Parsing is synchronous and runs on the event loop, so past this size the text is judged by its opening line alone.
_MAX_PARSE_CHARS = 32_768

# Parsing a shell command can make the compiler warn (``grep "\d+"`` holds an invalid Python escape). The router parses
# under its own file name, so one process-wide filter silences exactly that and leaves every other warning alone.
_ROUTER_FILENAME = "<command-router>"
warnings.filterwarnings("ignore", category=SyntaxWarning, module=re.escape(_ROUTER_FILENAME))

# Constructs a shell command line cannot contain: text that parses and holds one of them is Python.
_PYTHON_ONLY_NODES: tuple[type[ast.AST], ...] = (
    ast.Import,
    ast.ImportFrom,
    ast.FunctionDef,
    ast.AsyncFunctionDef,
    ast.ClassDef,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.If,
    ast.AugAssign,
    ast.AnnAssign,
    ast.Delete,
    ast.Raise,
    ast.Assert,
    ast.Await,
    ast.Match,
)

# What text that does not parse may still open with to be Python: the interpreter then reports its SyntaxError,
# which tells the model more than a shell's "command not found".
_PYTHON_OPENING_RE = re.compile(
    r"^(?:import\s+[A-Za-z_]|from\s+[A-Za-z_.]+\s+import\b|def\s+[A-Za-z_]|async\s+def\s|class\s+[A-Za-z_])"
)


class CodeType(StrEnum):
    PYTHON = "python"
    BASH = "bash"


@dataclass
class CodeDetectionResult:
    code_type: CodeType
    extracted_code: str
    detection_reason: str = ""


def _first_code_line(text: str) -> str:
    """The first line that is neither blank nor a comment, stripped."""
    for line in text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""


def _parse(text: str) -> ast.Module | None:
    """The syntax tree of ``text``, or ``None`` when it is too large or does not parse."""
    if len(text) > _MAX_PARSE_CHARS:
        return None
    try:
        return ast.parse(text, filename=_ROUTER_FILENAME)
    except PYTHON_PARSE_ERRORS:
        return None


def _python_evidence(text: str) -> str | None:
    """Why ``text`` is Python, or ``None`` when a shell should run it.

    A shell command that parses as Python is mostly a bare word or an arithmetic-looking line (``ls``, ``ls -la``,
    ``FOO=bar``), so parsing alone proves nothing: the text needs a construct a shell line cannot be. It is a pure
    function of the text, because the executor, the permission preflight and the tool's guards each ask about the
    same command and must get the same answer.
    """
    stripped = text.strip()
    if not stripped:
        return None
    tree = _parse(stripped)
    if tree is None:
        return "python opening statement" if _PYTHON_OPENING_RE.match(_first_code_line(stripped)) else None
    for node in ast.walk(tree):
        if isinstance(node, _PYTHON_ONLY_NODES):
            return f"python statement: {type(node).__name__}"
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            return "python call statement"
        # Not any assignment: ``OUT=result.txt`` and ``FLAGS=-la`` parse as ones too, while a shell word cannot hold a call.
        if isinstance(node, ast.Assign) and any(isinstance(inner, ast.Call) for inner in ast.walk(node.value)):
            return "python assignment from a call"
    return None


class CodeTypeDetector:
    """Detect Python vs Bash and extract Python from ``python -c`` commands.

    Detection order:
    1. ``python -c`` → Python (quote-aware extract, raw fallback on failure)
    2. ``extract_python_from_bash`` → heredoc / cat-heredoc / pure skill imports
    3. The text parses and holds a construct a shell line cannot (an import, a ``def``, a loop, a call statement,
       an assignment from a call, ``await``), or it does not parse but opens like Python → Python
    4. Default → Bash
    """

    _RAW_PYTHON_C_RE = re.compile(r"python3?\s+-c\s+(.+)", re.DOTALL)

    def detect(self, command: str) -> CodeDetectionResult:
        if self._is_python_command(command):
            extracted = self._extract_python_code_from_command(command)
            if extracted:
                return CodeDetectionResult(
                    code_type=CodeType.PYTHON,
                    extracted_code=extracted,
                    detection_reason="python -c command (extracted)",
                )
            return CodeDetectionResult(
                code_type=CodeType.PYTHON,
                extracted_code=self._raw_extract_python_c(command),
                detection_reason="python -c command (raw fallback after quote extraction failed)",
            )

        embedded = extract_python_from_bash(command)
        if embedded is not None:
            return CodeDetectionResult(
                code_type=CodeType.PYTHON,
                extracted_code=embedded,
                detection_reason="embedded python extracted from bash wrapper",
            )

        evidence = _python_evidence(command)
        if evidence:
            return CodeDetectionResult(
                code_type=CodeType.PYTHON,
                extracted_code=command,
                detection_reason=evidence,
            )

        return CodeDetectionResult(
            code_type=CodeType.BASH,
            extracted_code=command,
            detection_reason="default to bash",
        )

    def _is_python_command(self, command: str) -> bool:
        return bool(re.search(r"python3?\s+-c", command))

    def _extract_python_code_from_command(self, command: str) -> str | None:
        return extract_python_from_bash(command)

    def _raw_extract_python_c(self, command: str) -> str:
        match = self._RAW_PYTHON_C_RE.search(command)
        if not match:
            return command

        rest = match.group(1).strip()
        if len(rest) >= 2 and rest[0] in ("'", '"') and rest[-1] == rest[0]:
            return rest[1:-1]
        return rest


code_detector = CodeTypeDetector()


def detect_for_execution(command: str) -> CodeDetectionResult:
    """The route the bash tool gives ``command``: the executor strips it and unwraps one Markdown fence first.

    A check that depends on the language of a command asks here, so a command is judged in the language it runs
    in: Python wrapped in a fence is still Python.
    """
    return code_detector.detect(unwrap_markdown_fence(command.strip()))


def runs_as_python(command: str, *, run_in_background: bool = False) -> bool:
    """Whether the bash tool hands ``command`` to the Python wrapper instead of a shell.

    A background spawn is always read by a shell, whatever the text looks like. Otherwise the route is
    ``detect_for_execution``'s, so a check that only makes sense for shell syntax can stand down exactly when
    no shell reads the text.
    """
    return not run_in_background and detect_for_execution(command).code_type == CodeType.PYTHON
