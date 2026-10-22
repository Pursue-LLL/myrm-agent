"""Architecture test: server product code must not branch on test-only env vars.

Business behaviour is selected by configuration and injected values, not by a pytest/E2E
switch. Historically `MYRM_E2E_SHPOIB` sat inside the config loader and the agent stream
entrypoint, which meant the test harness could change production semantics and a real
capability (an instance that cannot multiplex) was expressed as an E2E flag instead of a
deployment capability. Both are now modelled explicitly, so this test keeps them out.
"""

from __future__ import annotations

import re
from pathlib import Path

_APP_ROOT = Path(__file__).resolve().parent.parent.parent / "app"

# Test-runner switches that are legitimately readable: pytest sets them itself, and the
# only consumers are "am I running under pytest" probes that suppress developer-facing
# preflight warnings.
_ALLOWED = frozenset({"PYTEST_CURRENT_TEST"})

_ENV_READ = re.compile(r"""\b(?:os\.getenv|os\.environ\.get|os\.environ\[)\s*\(?\s*["']([A-Z][A-Z0-9_]*)["']""")


def _app_python_files() -> list[Path]:
    return sorted(_APP_ROOT.rglob("*.py"))


def test_app_reads_no_test_only_env_vars() -> None:
    offenders: list[str] = []
    for path in _app_python_files():
        text = path.read_text(encoding="utf-8")
        for match in _ENV_READ.finditer(text):
            name = match.group(1)
            if name.startswith(("MYRM_E2E_", "MYRM_TEST_", "E2E_")) and name not in _ALLOWED:
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(_APP_ROOT)}:{line_no}: {name}")

    assert offenders == [], "test-only env vars read by product code:\n" + "\n".join(offenders)


def test_app_reads_no_embedding_env_vars() -> None:
    """Embedding/search/reranker credentials are WebUI business config, never process env."""
    offenders: list[str] = []
    for path in _app_python_files():
        text = path.read_text(encoding="utf-8")
        for match in _ENV_READ.finditer(text):
            name = match.group(1)
            if name.startswith(("EMBEDDING_", "RERANKER_", "BASIC_", "LITE_", "TAVILY_")):
                line_no = text[: match.start()].count("\n") + 1
                offenders.append(f"{path.relative_to(_APP_ROOT)}:{line_no}: {name}")

    assert offenders == [], "business credentials read from process env by product code:\n" + "\n".join(offenders)
