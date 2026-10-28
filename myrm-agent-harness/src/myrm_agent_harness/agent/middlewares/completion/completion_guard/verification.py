"""Verification command classification: is a bash command a test, lint, type-check or build run.

[INPUT]
- agent.security.guards.loop_guard::VerificationCategory (POS: the kinds of verification a command can be)

[OUTPUT]
- classify_verification(): the verification category of a bash tool call, or None

[POS]
Tells the guard which recorded bash calls count as verification of code the run wrote. A command is split into
shell segments (quote-aware, on ``&&`` ``||`` ``;`` ``&``), each segment is stripped of what only launches the real
program (environment assignments, ``timeout``, ``uv run``, ``npx``, interpreter and ``.venv/bin`` paths), and the
program plus its leading arguments are matched on whole tokens. Token matching keeps ``pip install pytest`` and
``npm test-helper`` from counting; the stripping keeps ``FOO=1 npm test`` and ``uv run pytest`` from being missed.
"""

from __future__ import annotations

import re

from myrm_agent_harness.agent.security.guards.loop_guard import VerificationCategory

_TEST = VerificationCategory.TEST
_LINT = VerificationCategory.LINT
_TYPECHECK = VerificationCategory.TYPECHECK
_BUILD = VerificationCategory.BUILD

_PATTERNS: dict[tuple[str, ...], VerificationCategory] = {
    ("pytest",): _TEST,
    ("jest",): _TEST,
    ("vitest",): _TEST,
    ("deno", "test"): _TEST,
    ("cargo", "test"): _TEST,
    ("go", "test"): _TEST,
    ("dotnet", "test"): _TEST,
    ("mvn", "test"): _TEST,
    ("gradle", "test"): _TEST,
    ("bun", "test"): _TEST,
    # Running a program is a smoke run of what the model wrote.
    ("python",): _TEST,
    ("node",): _TEST,
    ("ts-node",): _TEST,
    ("bun", "run"): _TEST,
    ("deno", "run"): _TEST,
    ("go", "run"): _TEST,
    ("ruby",): _TEST,
    ("php",): _TEST,
    ("java",): _TEST,
    ("ruff", "check"): _LINT,
    ("ruff", "format"): _LINT,
    ("eslint",): _LINT,
    ("flake8",): _LINT,
    ("pylint",): _LINT,
    ("biome", "check"): _LINT,
    ("biome", "lint"): _LINT,
    ("prettier",): _LINT,
    ("black",): _LINT,
    ("isort",): _LINT,
    ("clippy",): _LINT,
    ("cargo", "clippy"): _LINT,
    ("golangci-lint",): _LINT,
    ("go", "vet"): _LINT,
    ("mypy",): _TYPECHECK,
    ("pyright",): _TYPECHECK,
    ("tsc",): _TYPECHECK,
    ("gcc",): _BUILD,
    ("g++",): _BUILD,
    ("javac",): _BUILD,
    ("cargo", "build"): _BUILD,
    ("cargo", "check"): _BUILD,
    ("go", "build"): _BUILD,
    ("dotnet", "build"): _BUILD,
    ("gradle", "build"): _BUILD,
}


def _group_by_program() -> dict[str, tuple[tuple[tuple[str, ...], VerificationCategory], ...]]:
    """Patterns grouped by their program, longest first, so a two-token pattern is tried before a one-token one."""
    grouped: dict[str, list[tuple[tuple[str, ...], VerificationCategory]]] = {}
    for pattern, category in sorted(_PATTERNS.items(), key=lambda item: len(item[0]), reverse=True):
        grouped.setdefault(pattern[0], []).append((pattern, category))
    return {program: tuple(entries) for program, entries in grouped.items()}


_PATTERNS_BY_PROGRAM = _group_by_program()

# ``scripts`` entries of package.json and ``make`` targets: the name before ``:`` decides (``test:unit`` is a test).
_SCRIPT_CATEGORIES: dict[str, VerificationCategory] = {
    "test": _TEST,
    "lint": _LINT,
    "typecheck": _TYPECHECK,
    "type-check": _TYPECHECK,
    "build": _BUILD,
}
_MAKE_TARGETS: dict[str, VerificationCategory] = {**_SCRIPT_CATEGORIES, "tests": _TEST, "check": _TEST}

_PROGRAM_ALIASES = {"gradlew": "gradle", "mvnw": "mvn"}
_PYTHON = re.compile(r"python(?:\d+(?:\.\d+)*)?")
_NON_VERIFYING_PYTHON_MODULES = frozenset({"pip", "venv", "ensurepip"})

_PLAIN_WRAPPERS = frozenset({"env", "time", "nohup", "npx", "bunx", "uvx"})
_SUBCOMMAND_WRAPPERS = frozenset(
    {
        ("uv", "run"),
        ("poetry", "run"),
        ("pdm", "run"),
        ("pipenv", "run"),
        ("pnpm", "exec"),
        ("pnpm", "dlx"),
        ("yarn", "dlx"),
        ("npm", "exec"),
    }
)
_OPTIONS_WITH_VALUE = frozenset(
    {"--with", "--from", "--python", "-p", "--package", "--project", "--directory", "--group", "--extra"}
    | {"--env-file", "-u", "-k", "-s", "--signal", "--kill-after"}
)
_ENV_ASSIGNMENT = re.compile(r"[a-z_][a-z0-9_]*=")
_DURATION = re.compile(r"\d+(?:\.\d+)?[smhd]?")

# Shell words, with quoted spans kept inside their word so ``-m "a; pytest"`` is never split. A stray quote
# falls through to ``\S`` instead of raising, so an unbalanced heredoc body cannot hide the command.
_TOKEN = re.compile(r"""&&|\|\||[;&()]|[<>]+&?|(?:[^\s;&|()<>"']|"(?:\\.|[^"\\])*"|'[^']*')+|\S""")
_SEGMENT_BREAKS = frozenset({"&&", "||", ";", "&", "(", ")"})


def _segments(command: str) -> list[list[str]]:
    segments: list[list[str]] = [[]]
    for token in _TOKEN.findall(command):
        if token in _SEGMENT_BREAKS:
            segments.append([])
        else:
            segments[-1].append(token)
    return segments


def _program(token: str) -> str:
    """The program a command word runs: path and version suffixes are not part of its identity."""
    name = token.rsplit("/", 1)[-1]
    name = _PROGRAM_ALIASES.get(name, name)
    return "python" if _PYTHON.fullmatch(name) else name


def _skip_options(tokens: list[str], index: int) -> int:
    while index < len(tokens) and tokens[index].startswith("-"):
        index += 2 if tokens[index] in _OPTIONS_WITH_VALUE else 1
    return index


def _strip_launchers(tokens: list[str]) -> list[str]:
    """Drop environment assignments and wrappers that only start the program being verified."""
    index = 0
    while index < len(tokens):
        token = tokens[index]
        program = _program(token)
        if _ENV_ASSIGNMENT.match(token):
            index += 1
        elif program in _PLAIN_WRAPPERS:
            index = _skip_options(tokens, index + 1)
        elif program == "timeout":
            index = _skip_options(tokens, index + 1)
            if index < len(tokens) and _DURATION.fullmatch(tokens[index]):
                index += 1
        elif (program, *tokens[index + 1 : index + 2]) in _SUBCOMMAND_WRAPPERS:
            index = _skip_options(tokens, index + 2)
        else:
            break
    return tokens[index:]


def _script_category(program: str, args: list[str]) -> VerificationCategory | None:
    """Category of ``npm|pnpm|yarn|bun run <script>`` (and the ``pnpm lint`` shorthand) or ``make <target>``."""
    if program == "make":
        target = next((arg for arg in args if not arg.startswith("-")), "")
        return _MAKE_TARGETS.get(target)
    if program not in {"npm", "pnpm", "yarn", "bun"} or not args:
        return None
    head = args[0]
    if head in {"run", "run-script"}:
        script = args[1] if len(args) > 1 else ""
    elif program in {"pnpm", "yarn"} or head == "test":
        script = head
    else:
        return None
    return _SCRIPT_CATEGORIES.get(script.split(":", 1)[0])


def _classify_segment(tokens: list[str]) -> VerificationCategory | None:
    tokens = _strip_launchers(tokens)
    if not tokens:
        return None
    program, args = _program(tokens[0]), tokens[1:]
    if program == "python" and args[:1] == ["-m"] and args[1:2] and args[1] in _NON_VERIFYING_PYTHON_MODULES:
        return None
    category = _script_category(program, args)
    if category is not None:
        return category
    for pattern, pattern_category in _PATTERNS_BY_PROGRAM.get(program, ()):
        if tuple(args[: len(pattern) - 1]) == pattern[1:]:
            return pattern_category
    return None


def classify_verification(tool_args: dict[str, object]) -> VerificationCategory | None:
    """Detect if a bash command is a verification action (test/lint/typecheck/build).

    The first shell segment that runs a known verification program decides. Matching is on whole tokens, so
    ``pip install pytest`` does not match ``pytest`` and ``npm test-helper`` does not match ``npm test``.
    """
    command = str(tool_args.get("command", "")).strip()
    if not command:
        return None
    for segment in _segments(command.lower()):
        category = _classify_segment(segment)
        if category is not None:
            return category
    return None


__all__ = ["classify_verification"]
