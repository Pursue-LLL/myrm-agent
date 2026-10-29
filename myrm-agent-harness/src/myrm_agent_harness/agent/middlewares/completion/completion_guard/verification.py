"""Verification command classification: is a bash command a test, lint, type-check or build run, and did it fail.

[INPUT]
- agent.security.guards.loop_guard::VerificationCategory (POS: the kinds of verification a command can be)
- agent.security.guards.loop_guard::CallRecord, SuccessLevel (POS: the recorded call and how its output was judged)

[OUTPUT]
- classify_verification(): the verification category of a bash tool call, or None
- tag_verification_call(): records the category on a finished bash call and fails it when its exit code says so

[POS]
Tells the guard which recorded bash calls count as verification of code the run wrote, and whether each passed.
A command is split into shell segments (quote-aware, on ``&&`` ``||`` ``;`` ``&``), each segment is stripped of what
only launches the real program (environment assignments, ``timeout``, ``uv run``, ``npx``, interpreter and
``.venv/bin`` paths), and the program plus its leading arguments are matched on whole tokens. Token matching keeps
``pip install pytest`` and ``npm test-helper`` from counting; the stripping keeps ``FOO=1 npm test`` and
``uv run pytest`` from being missed.
The output judge reads text for failure keywords, which ruff, tsc and a summary-only pytest run do not print; the
exit code the bash tool appends is what marks those runs failed. The shell reports the status of the last command it
ran, so the exit code is held against a command only when its last pipeline stage is itself a verification.
"""

from __future__ import annotations

import re

from myrm_agent_harness.agent.security.guards.loop_guard import CallRecord, SuccessLevel, VerificationCategory

_TEST = VerificationCategory.TEST
_LINT = VerificationCategory.LINT
_TYPECHECK = VerificationCategory.TYPECHECK
_BUILD = VerificationCategory.BUILD

# The bash tool ends the result of a command that exited non-zero with ``[exit_code: N]``.
_EXIT_MARKER = re.compile(r"\[exit_code: (-?\d+)")
# 124 is a timeout and 137 a SIGKILL (the tool's own hints); above 127 or negative is a signal. Those say the
# run was cut short, not that the checks it runs failed.
_TIMED_OUT = 124
_LAST_PROGRAM_EXIT = 127
_JUDGED_PASSING = frozenset({SuccessLevel.FULL_SUCCESS, SuccessLevel.PARTIAL_SUCCESS})

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


def _command(tool_args: dict[str, object]) -> str:
    return str(tool_args.get("command", "")).strip()


def classify_verification(tool_args: dict[str, object]) -> VerificationCategory | None:
    """Detect if a bash command is a verification action (test/lint/typecheck/build).

    The first shell segment that runs a known verification program decides. Matching is on whole tokens, so
    ``pip install pytest`` does not match ``pytest`` and ``npm test-helper`` does not match ``npm test``.
    """
    command = _command(tool_args)
    if not command:
        return None
    for segment in _segments(command.lower()):
        category = _classify_segment(segment)
        if category is not None:
            return category
    return None


def _exited_with_failure(result_text: str) -> bool:
    """True when the bash tool reported a program exit code that means the command's checks failed.

    The last marker is the shell's own: the tool appends it after all output, so earlier text that quotes one is
    output. A result without a marker (exit 0, or a run still going in the background) is not a failure.
    """
    markers = _EXIT_MARKER.findall(result_text)
    if not markers:
        return False
    code = int(markers[-1])
    return 1 <= code <= _LAST_PROGRAM_EXIT and code != _TIMED_OUT


def _ends_with_verification(command: str) -> bool:
    """True when the last command the line runs is itself a verification.

    The shell reports the status of the last command it ran, so the exit line belongs to a verification only when
    nothing runs after it: ``pytest -q && rg slow`` exits 1 when ``rg`` finds nothing, and a pipeline's status is its
    last stage's. A non-zero status after an earlier ``&&`` part cannot be told from that part failing, so such a
    command keeps the output judge's verdict.
    """
    segments = [segment for segment in _segments(command.lower()) if segment]
    if not segments:
        return False
    last = segments[-1]
    last_pipe = max((index for index, token in enumerate(last) if token == "|"), default=-1)
    return _classify_segment(last[last_pipe + 1 :]) is not None


def tag_verification_call(record: CallRecord, tool_args: dict[str, object], result_text: str) -> None:
    """Record which kind of verification a finished bash call was; a failing exit code overrules a passing read.

    ``result_text`` is the untruncated tool result: budget truncation can cut the exit line off. Only a call the
    output judge read as passing is changed, so an empty verification (no tests collected) keeps its own verdict,
    and only a command that ends with the verification, since the exit code is that of the last command it ran.
    """
    category = classify_verification(tool_args)
    if category is None:
        return
    record.verification_type = category
    if (
        record.success_level in _JUDGED_PASSING
        and _exited_with_failure(result_text)
        and _ends_with_verification(_command(tool_args))
    ):
        record.success_level = SuccessLevel.FAILURE


__all__ = ["classify_verification", "tag_verification_call"]
