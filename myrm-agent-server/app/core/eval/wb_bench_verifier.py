"""WorkBuddy Bench verifier assertion builder.

[INPUT]
- Path to a task directory (tests/verifier.toml, tests/scoring.py, ...)
- myrm_agent_harness.eval::SandboxAssertion

[OUTPUT]
- _test_suite_assertion_for(): Rule judge assertion for a task's native grader

[POS]
Builds the ``test_suite`` sandbox assertion that runs a task's official
grading protocol after agent execution. Splitting this out of
``wb_bench_workspace`` keeps workspace provisioning and grading wiring in
separate single-responsibility modules.

Grading follows the official WBBench ``tests/verifier.toml`` protocol instead of
the Harbor stub ``tests/test.sh`` (which always exits 64). Five native wiring
paths are supported:

- ``script_verifier`` family: run tests/verifier.py (WORKSPACE/LOG_DIR env).
- ``pytest_injected`` family: inject tests/injected/tests/ then run the whole
  declared ``[run] command`` (pytest or a custom test runner).
- ``repo_understanding`` family: run tests/scorer.py against the seeded repo.
- Office verifier (no family, only ``schema_version`` + ``[run] command``):
  run the whole declared pytest grading command against ``/tests/grading``.
- Security track (no verifier.toml): run tests/scoring.py / test_outputs.py,
  which writes ``reward.json`` directly.

Grading assets stay in the source cache and are mounted read-only via
``SandboxAssertion.readonly_paths``; the live agent workspace is addressed
through the ``{workspace}`` placeholder the harness expands at grading time, so
``gold.patch`` never reaches the agent.
"""

from __future__ import annotations

import logging
import re
import tomllib
from pathlib import Path

from myrm_agent_harness.eval import SandboxAssertion

logger = logging.getLogger(__name__)


def _read_verifier_toml(task_dir: Path) -> dict[str, object] | None:
    """Parse the official ``tests/verifier.toml`` grading protocol, or None when absent."""
    path = task_dir / "tests" / "verifier.toml"
    if not path.is_file():
        return None
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except (tomllib.TOMLDecodeError, OSError) as exc:
        logger.warning("Invalid verifier.toml for %s: %s", task_dir.name, exc)
        return None


def _flatten_shell_command(command: str) -> str:
    """Collapse backslash line continuations into single spaces.

    Applies to the whole declared ``[run] command`` (pytest or a custom test
    runner). Harbor verifier commands are written with trailing ``\\`` + newline
    continuations. A lone trailing continuation would leave bash waiting for
    more input, so every continuation (including a trailing one with no newline
    after it) is flattened.
    """
    return re.sub(r"\\\s*\n\s*", " ", command).rstrip().removesuffix("\\").strip()


def _verifier_run_command(
    verifier: dict[str, object], tests_dir: Path
) -> str | None:
    """Return the declared ``[run] command`` with Harbor paths rewritten.

    The whole command is preserved (pytest, custom test runners, redirections)
    so every declared grader executes faithfully; only Harbor mounts are
    rewritten to the local sandbox layout. A leading inline ``PYTHONPATH="..."``
    prefix that expands the workspace via shell ``${...}`` fallback is dropped
    (the sandbox command validator blocks ``${}`` expansion) — callers inject
    ``PYTHONPATH`` themselves.
    """
    run = verifier.get("run")
    if not isinstance(run, dict):
        return None
    command = run.get("command")
    if not isinstance(command, str):
        return None
    command = _flatten_shell_command(command)
    # Harbor Office commands prefix an inline PYTHONPATH that expands the
    # workspace via shell `${...}` fallback, which the sandbox command
    # validator blocks. Drop the prefix; the caller injects PYTHONPATH.
    command = re.sub(r'^PYTHONPATH="[^"]*"\s+', "", command)
    return _rewrite_harbor_paths(command, tests_dir)


def _rewrite_harbor_paths(value: str, tests_dir: Path) -> str:
    """Rewrite Harbor-mounted absolute paths to local sandbox equivalents.

    Office verifier.toml commands/env reference ``/tests/...`` (grading assets),
    ``/workspace`` (agent workspace) and ``/logs/verifier/...`` (verifier logs).
    A token shields the expanded ``tests_dir`` (whose own path contains
    ``/tests/``) so a later replace can never re-match it.
    """
    return (
        value.replace("/tests/", "___TESTS___/")
        .replace("/logs/verifier/", "{workspace}/.wb_bench/")
        .replace("/workspace", "{workspace}")
        .replace("___TESTS___", str(tests_dir))
    )


def _office_run_assertion(
    verifier: dict[str, object],
    tests_dir: Path,
    timeout: int,
) -> SandboxAssertion | None:
    """Build the Rule assertion for an Office verifier (no ``family`` key).

    Office ``verifier.toml`` files carry ``schema_version =
    "workbuddy.office.verifier.v1"``, a ``[run] command`` that invokes pytest
    against ``/tests/grading``, and ``[env]`` variables pointing at grading
    assets. The whole command and env are rewritten so the grading run executes
    on a plain sandbox: grading assets stay in the source cache (mounted
    read-only), the live agent workspace resolves through ``{workspace}``, and
    the JUnit report lands in ``{workspace}/.wb_bench/``.
    """
    command = _verifier_run_command(verifier, tests_dir)
    if command is None:
        return None
    env_parts = ["PYTHONPATH={workspace}"] + [
        f"{key}={_rewrite_harbor_paths(value, tests_dir)}"
        for key, value in _iter_verifier_env(verifier)
    ]
    return SandboxAssertion(
        type="test_suite",
        target=(
            f"mkdir -p {{workspace}}/.wb_bench && rm -f {{workspace}}/.wb_bench/results.xml && "
            f"cd {{workspace}} && {' '.join(env_parts)} {command}"
        ),
        result_file="{workspace}/.wb_bench/results.xml",
        timeout=timeout,
        readonly_paths=(str(tests_dir),),
    )


def _iter_verifier_env(verifier: dict[str, object]) -> list[tuple[str, str]]:
    """Return the declared ``[env]`` string pairs in declaration order."""
    env = verifier.get("env")
    if not isinstance(env, dict):
        return []
    return [(key, value) for key, value in env.items() if isinstance(value, str)]


_DIRECT_SCORER_NAMES = ("scoring.py", "test_outputs.py")


def _direct_scorer_assertion(
    tests_dir: Path,
    timeout: int,
) -> SandboxAssertion | None:
    """Build the Rule assertion for a task scored by a standalone scorer script.

    The official Security track ships ``tests/scoring.py`` (or
    ``test_outputs.py``) that writes a numeric ``reward.json`` directly, with no
    ``verifier.toml``. The scorer runs against the live agent workspace with the
    grading assets mounted read-only; the reward file resolves through the
    ``score.json``/``reward.json`` candidates in the workspace.
    """
    scorer = next(
        (
            tests_dir / name
            for name in _DIRECT_SCORER_NAMES
            if (tests_dir / name).is_file()
        ),
        None,
    )
    if scorer is None:
        return None
    return SandboxAssertion(
        type="test_suite",
        target=f"cd {{workspace}} && WORKSPACE={{workspace}} python3 {scorer}",
        result_file="{workspace}/reward.json",
        timeout=timeout,
        readonly_paths=(str(tests_dir),),
    )


def _test_suite_assertion_for(task_dir: Path) -> SandboxAssertion | None:
    """Build the Rule judge assertion driven by a task's native verifier.

    Wires the family-specific grading command (script_verifier / pytest_injected /
    repo_understanding), the Office ``[run] command`` pytest grading, or the
    Security standalone scorer. Grading assets stay in the source cache and are
    mounted read-only via ``SandboxAssertion.readonly_paths``; the live agent
    workspace is addressed through the ``{workspace}`` placeholder the harness
    expands at grading time. Returns None when the task ships no supported
    verifier (e.g. Web composite track that needs a VLM judge pipeline).
    """
    verifier = _read_verifier_toml(task_dir)
    tests_dir = task_dir / "tests"
    timeout = 600

    # Office-family verifier: no ``family`` key, only schema_version +
    # [run] command / [env]. Its grading run still gives a deterministic
    # pass_rate, so it is wired instead of falling back to the VLM pipeline.
    if verifier is not None and not verifier.get("family"):
        return _office_run_assertion(verifier, tests_dir, timeout)

    family = str(verifier.get("family", "")) if verifier else ""

    if family == "script_verifier":
        verifier_py = tests_dir / "verifier.py"
        if not verifier_py.is_file():
            return None
        return SandboxAssertion(
            type="test_suite",
            target=(
                f"WORKSPACE={{workspace}} LOG_DIR={{workspace}}/.wb_bench/logs "
                f"python3 {verifier_py}"
            ),
            result_file="{workspace}/.wb_bench/logs/reward.txt",
            timeout=timeout,
            readonly_paths=(str(tests_dir),),
        )

    if family == "pytest_injected":
        injected = tests_dir / "injected" / "tests"
        if not injected.is_dir():
            injected = tests_dir / "injected"
        pytest_cmd = _verifier_run_command(verifier, tests_dir) if verifier else None
        if not injected.is_dir() or not pytest_cmd:
            return None
        return SandboxAssertion(
            type="test_suite",
            target=(
                f"mkdir -p {{workspace}}/tests {{workspace}}/.wb_bench && "
                f"rm -f {{workspace}}/.wb_bench/results.xml && "
                f"cp -r {injected}/. {{workspace}}/tests/ && cd {{workspace}} && {pytest_cmd}"
            ),
            result_file="{workspace}/.wb_bench/results.xml",
            timeout=timeout,
            readonly_paths=(str(tests_dir),),
        )

    if family == "repo_understanding":
        scorer = tests_dir / "scorer.py"
        if not scorer.is_file():
            return None
        return SandboxAssertion(
            type="test_suite",
            target=(
                f"mkdir -p {{workspace}}/.wb_bench/logs && "
                f"python3 {scorer} --repo {{workspace}} --output {{workspace}}/.wb_bench/reward.json"
            ),
            result_file="{workspace}/.wb_bench/reward.json",
            timeout=timeout,
            readonly_paths=(str(tests_dir),),
        )

    # Security track: tasks ship tests/scoring.py (or test_outputs.py) that
    # writes reward.json directly, with no verifier.toml.
    return _direct_scorer_assertion(tests_dir, timeout)
