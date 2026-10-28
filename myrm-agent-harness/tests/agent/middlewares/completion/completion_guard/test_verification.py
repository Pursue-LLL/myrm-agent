"""Which bash commands count as verification (test, lint, type-check, build)."""

from __future__ import annotations

import pytest

from myrm_agent_harness.agent.middlewares.completion.completion_guard import (
    classify_verification,
)
from myrm_agent_harness.agent.middlewares.completion.completion_guard.verification import detect_verification
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


class TestClassifyWrappedCommands:
    """A runner, interpreter path, environment or timeout in front does not change what the command verifies."""

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("uv run pytest -q", VerificationCategory.TEST),
            ("uv run --frozen pytest -q", VerificationCategory.TEST),
            ("uv run python -m pytest", VerificationCategory.TEST),
            ("uvx ruff check .", VerificationCategory.LINT),
            ("poetry run pytest", VerificationCategory.TEST),
            ("python3 -m pytest -q", VerificationCategory.TEST),
            ("python3.12 -m pytest", VerificationCategory.TEST),
            (".venv/bin/pytest -q", VerificationCategory.TEST),
            ("venv/bin/python -m pytest", VerificationCategory.TEST),
            ("./node_modules/.bin/jest", VerificationCategory.TEST),
            ("FOO=1 pytest", VerificationCategory.TEST),
            ("PYTHONPATH=. CI=1 pytest -q", VerificationCategory.TEST),
            ("FOO=1 npm test", VerificationCategory.TEST),
            ("timeout 60 pytest", VerificationCategory.TEST),
            ("timeout --foreground 120 cargo test", VerificationCategory.TEST),
            ("time pytest", VerificationCategory.TEST),
            ("env CI=1 pytest", VerificationCategory.TEST),
            ("npx vitest run", VerificationCategory.TEST),
            ("npx -y vitest run", VerificationCategory.TEST),
            ("bunx tsc --noEmit", VerificationCategory.TYPECHECK),
            ("pnpm exec tsc --noEmit", VerificationCategory.TYPECHECK),
            ("cd sub && uv run pytest", VerificationCategory.TEST),
            ("cd sub && FOO=1 timeout 60 pytest -q", VerificationCategory.TEST),
            ("pytest -q 2>&1 | tail -5", VerificationCategory.TEST),
        ],
    )
    def test_wrapped_command_is_classified_like_the_bare_one(
        self, command: str, expected: VerificationCategory
    ) -> None:
        assert classify_verification({"command": command}) == expected

    @pytest.mark.parametrize(
        ("command", "expected"),
        [
            ("make test", VerificationCategory.TEST),
            ("make check", VerificationCategory.TEST),
            ("make lint", VerificationCategory.LINT),
            ("make typecheck", VerificationCategory.TYPECHECK),
            ("make build", VerificationCategory.BUILD),
            ("npm run lint", VerificationCategory.LINT),
            ("npm run typecheck", VerificationCategory.TYPECHECK),
            ("npm run type-check", VerificationCategory.TYPECHECK),
            ("pnpm lint", VerificationCategory.LINT),
            ("pnpm typecheck", VerificationCategory.TYPECHECK),
            ("pnpm build", VerificationCategory.BUILD),
            ("yarn lint", VerificationCategory.LINT),
            ("bun run lint", VerificationCategory.LINT),
            ("bun run typecheck", VerificationCategory.TYPECHECK),
            ("npm run test:unit", VerificationCategory.TEST),
            ("pnpm test:e2e", VerificationCategory.TEST),
            ("cargo clippy", VerificationCategory.LINT),
            ("cargo check", VerificationCategory.BUILD),
            ("go vet ./...", VerificationCategory.LINT),
            ("jest --ci", VerificationCategory.TEST),
            ("./gradlew test", VerificationCategory.TEST),
            ("./mvnw test", VerificationCategory.TEST),
        ],
    )
    def test_project_script_and_build_tool_forms(self, command: str, expected: VerificationCategory) -> None:
        assert classify_verification({"command": command}) == expected

    @pytest.mark.parametrize(
        "command",
        [
            "uv pip install pytest",
            "uv sync",
            "pip install pytest",
            "npx create-react-app app",
            "FOO=1 ls",
            "timeout 60 sleep 5",
            "echo pytest",
            "grep -r pytest .",
            "cat .venv/bin/pytest",
            "git commit -m 'run pytest'",
            "make install",
            "python3 -m pip install pytest",
            "python -m venv .venv",
            'echo "run; pytest -q"',
            "echo 'cd x && pytest'",
            "npm run dev",
            "npm run lint-staged-setup",
            "pnpm install",
            "./run_tests.sh",
            "sh check.sh",
        ],
    )
    def test_non_verification_stays_unclassified(self, command: str) -> None:
        assert classify_verification({"command": command}) is None


class TestExitStatusIsItsOwn:
    """Whether the exit status of the whole command is the status of the verification it runs."""

    @pytest.mark.parametrize(
        "command",
        [
            "pytest",
            "pytest -q tests/",
            "cd sub && pytest",
            "pytest && echo ok",
            "uv run pytest -q",
            "FOO=1 npm test",
            "timeout 60 pytest",
            "pytest -k 'a or b'",
            "pytest 2>&1",
            "echo start; pytest",
        ],
    )
    def test_the_verification_is_what_decides_the_exit_status(self, command: str) -> None:
        detected = detect_verification({"command": command})

        assert detected is not None
        assert detected.exit_is_own

    @pytest.mark.parametrize(
        "command",
        [
            "pytest | tail -5",
            "pytest -q 2>&1 | tee out.log",
            "pytest | grep -c passed",
            "pytest || true",
            "pytest || echo failed",
            "pytest; echo done",
            "pytest & wait",
            "pytest\necho done",
            "(pytest) | cat",
        ],
    )
    def test_something_after_the_verification_decides_it_instead(self, command: str) -> None:
        detected = detect_verification({"command": command})

        assert detected is not None
        assert not detected.exit_is_own

    def test_a_command_that_verifies_nothing_is_not_detected(self) -> None:
        assert detect_verification({"command": "ls | tail"}) is None
        assert detect_verification({}) is None

    def test_the_category_is_the_one_classify_verification_gives(self) -> None:
        detected = detect_verification({"command": "uv run mypy src"})

        assert detected is not None
        assert detected.category == classify_verification({"command": "uv run mypy src"})
