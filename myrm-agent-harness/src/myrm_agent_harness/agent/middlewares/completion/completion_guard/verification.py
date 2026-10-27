"""Verification command classification: is a bash command a test, lint, type-check or build run.

[INPUT]
- agent.security.guards.loop_guard::VerificationCategory (POS: the kinds of verification a command can be)

[OUTPUT]
- classify_verification(): the verification category of a bash tool call, or None

[POS]
Tells the guard which recorded bash calls count as verification of code the run wrote. Word-boundary matching keeps
``pip install pytest`` and ``npm test-helper`` from counting.
"""

from __future__ import annotations

from myrm_agent_harness.agent.security.guards.loop_guard import VerificationCategory

_VERIFICATION_PATTERNS: dict[str, VerificationCategory] = {
    "pytest": VerificationCategory.TEST,
    "python -m pytest": VerificationCategory.TEST,
    "npm test": VerificationCategory.TEST,
    "npm run test": VerificationCategory.TEST,
    "npx jest": VerificationCategory.TEST,
    "yarn test": VerificationCategory.TEST,
    "bun test": VerificationCategory.TEST,
    "pnpm test": VerificationCategory.TEST,
    "pnpm run test": VerificationCategory.TEST,
    "deno test": VerificationCategory.TEST,
    "cargo test": VerificationCategory.TEST,
    "go test": VerificationCategory.TEST,
    "dotnet test": VerificationCategory.TEST,
    "mvn test": VerificationCategory.TEST,
    "gradle test": VerificationCategory.TEST,
    "vitest": VerificationCategory.TEST,
    "unittest": VerificationCategory.TEST,
    "python": VerificationCategory.TEST,
    "node": VerificationCategory.TEST,
    "ts-node": VerificationCategory.TEST,
    "bun run": VerificationCategory.TEST,
    "deno run": VerificationCategory.TEST,
    "go run": VerificationCategory.TEST,
    "ruby": VerificationCategory.TEST,
    "php": VerificationCategory.TEST,
    "gcc": VerificationCategory.BUILD,
    "g++": VerificationCategory.BUILD,
    "javac": VerificationCategory.BUILD,
    "java": VerificationCategory.TEST,
    "ruff check": VerificationCategory.LINT,
    "ruff format": VerificationCategory.LINT,
    "eslint": VerificationCategory.LINT,
    "flake8": VerificationCategory.LINT,
    "pylint": VerificationCategory.LINT,
    "biome check": VerificationCategory.LINT,
    "biome lint": VerificationCategory.LINT,
    "prettier": VerificationCategory.LINT,
    "black": VerificationCategory.LINT,
    "isort": VerificationCategory.LINT,
    "clippy": VerificationCategory.LINT,
    "golangci-lint": VerificationCategory.LINT,
    "mypy": VerificationCategory.TYPECHECK,
    "pyright": VerificationCategory.TYPECHECK,
    "tsc": VerificationCategory.TYPECHECK,
    "npx tsc": VerificationCategory.TYPECHECK,
    "cargo build": VerificationCategory.BUILD,
    "npm run build": VerificationCategory.BUILD,
    "yarn build": VerificationCategory.BUILD,
    "pnpm run build": VerificationCategory.BUILD,
    "bun run build": VerificationCategory.BUILD,
    "make build": VerificationCategory.BUILD,
    "go build": VerificationCategory.BUILD,
    "dotnet build": VerificationCategory.BUILD,
    "gradle build": VerificationCategory.BUILD,
}


def _is_command_at_boundary(cmd: str, pattern: str) -> bool:
    """Check if pattern matches at a word boundary (followed by space or end-of-string)."""
    return cmd == pattern or cmd.startswith(pattern + " ")


def classify_verification(tool_args: dict[str, object]) -> VerificationCategory | None:
    """Detect if a bash command is a verification action (test/lint/typecheck/build).

    Uses word-boundary matching to minimise false positives. For example,
    ``pip install pytest`` will NOT match because ``pytest`` does not appear
    at a command boundary, and ``npm test-helper`` will NOT match ``npm test``
    because the pattern is followed by ``-`` instead of a space or end-of-string.
    """
    command = str(tool_args.get("command", "")).strip()
    if not command:
        return None
    cmd_lower = command.lower()
    for pattern, category in sorted(_VERIFICATION_PATTERNS.items(), key=lambda x: len(x[0]), reverse=True):
        if _is_command_at_boundary(cmd_lower, pattern):
            return category
        for sep in (" && ", "; "):
            idx = cmd_lower.find(sep + pattern)
            if idx >= 0:
                tail = cmd_lower[idx + len(sep) :]
                if _is_command_at_boundary(tail, pattern):
                    return category
    return None


__all__ = ["classify_verification"]
