"""Which bash commands count as verification (test, lint, type-check, build)."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    classify_verification,
)
from myrm_agent_harness.agent.security.guards.loop_guard import (
    VerificationCategory,
)


class TestClassifyVerification:
    """Test classify_verification command detection."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("pytest tests/", VerificationCategory.TEST),
            ("python -m pytest -x", VerificationCategory.TEST),
            ("npm test", VerificationCategory.TEST),
            ("npm run test", VerificationCategory.TEST),
            ("cargo test", VerificationCategory.TEST),
            ("pnpm test", VerificationCategory.TEST),
            ("pnpm run test", VerificationCategory.TEST),
            ("deno test", VerificationCategory.TEST),
            ("ruff check src/", VerificationCategory.LINT),
            ("eslint .", VerificationCategory.LINT),
            ("golangci-lint run", VerificationCategory.LINT),
            ("mypy src/", VerificationCategory.TYPECHECK),
            ("npx tsc --noEmit", VerificationCategory.TYPECHECK),
            ("cargo build", VerificationCategory.BUILD),
            ("npm run build", VerificationCategory.BUILD),
            ("yarn build", VerificationCategory.BUILD),
            ("pnpm run build", VerificationCategory.BUILD),
            ("bun run build", VerificationCategory.BUILD),
        ],
    )
    def test_detects_verification_commands(self, command: str, expected: VerificationCategory) -> None:
        assert classify_verification({"command": command}) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "ls -la",
            "pip install pytest",
            "cat test.py",
            "echo hello",
            "git status",
            "npm test-helper",
            "npm test-setup --env prod",
        ],
    )
    def test_rejects_non_verification_commands(self, command: str) -> None:
        assert classify_verification({"command": command}) is None

    def test_empty_command(self) -> None:
        assert classify_verification({"command": ""}) is None
        assert classify_verification({}) is None

    def test_chained_commands(self) -> None:
        """Detects verification in chained commands (&&, ;)."""
        assert classify_verification({"command": "cd src && pytest tests/"}) == VerificationCategory.TEST
        assert classify_verification({"command": "cd src; ruff check ."}) == VerificationCategory.LINT

    def test_exact_match_without_trailing_args(self) -> None:
        """Exact command matches (no args after pattern)."""
        assert classify_verification({"command": "pytest"}) == VerificationCategory.TEST
        assert classify_verification({"command": "npm test"}) == VerificationCategory.TEST
        assert classify_verification({"command": "tsc"}) == VerificationCategory.TYPECHECK

    def test_chained_exact_match(self) -> None:
        """Chained commands with exact match at end."""
        assert classify_verification({"command": "cd dir && pytest"}) == VerificationCategory.TEST
        assert classify_verification({"command": "source .venv/bin/activate && mypy"}) == VerificationCategory.TYPECHECK
