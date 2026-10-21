"""Gap Toast Chrome E2E Contract — Dual-Plane SSOT for capability_gap UI tests.

Verification plane: tests/api + tests/integration (API SSE truth).
Experience plane: tests/e2e/*gap*chrome_e2e*.py (browser send + poll only).

Seed/fixture POST is allowed; consuming agent-stream SSE inside chrome_e2e body is not.
"""

from __future__ import annotations

import re
from pathlib import Path

GAP_TOAST_E2E_WALL_SEC: float = 480.0

_E2E_ROOT = Path(__file__).resolve().parents[1] / "e2e"

# Files matching this glob participate in the contract.
GAP_TOAST_E2E_GLOB = "*gap*chrome_e2e*.py"

# Allowed: seed routes, comments. Forbidden: streaming agent-stream in test body.
_AGENT_STREAM_PATH = re.compile(
    r"/api/v1/agents/agent-stream",
    re.IGNORECASE,
)
_STREAM_CONSUME = re.compile(
    r"(iter_lines\s*\(|for\s+\w+\s+in\s+resp\b|urlopen\s*\([^)]*agent-stream)",
    re.IGNORECASE,
)

# Short POST to seed/fixture endpoints is allowed even if path contains "stream" elsewhere.
_SEED_ALLOWLIST = re.compile(
    r"seed[-_]|/test/seed|seed-migration|seed-.*-fixture",
    re.IGNORECASE,
)


def gap_toast_chrome_e2e_files() -> list[Path]:
    return sorted(_E2E_ROOT.glob(GAP_TOAST_E2E_GLOB))


def find_agent_stream_violations(path: Path) -> list[str]:
    """Return human-readable violations for Gap Toast E2E Contract."""
    text = path.read_text(encoding="utf-8")
    if not _AGENT_STREAM_PATH.search(text):
        return []
    violations: list[str] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        if _SEED_ALLOWLIST.search(line):
            continue
        if _AGENT_STREAM_PATH.search(line) and _STREAM_CONSUME.search(text):
            violations.append(
                f"{path.name}:{line_no}: agent-stream path in gap chrome_e2e "
                "(use integration tier for API SSE; browser-only in E2E)"
            )
            break
        if _AGENT_STREAM_PATH.search(line) and ("urlopen" in line or "httpx" in line and "stream" in line):
            violations.append(f"{path.name}:{line_no}: HTTP client to agent-stream forbidden in gap E2E")
    return violations


def collect_gap_toast_contract_violations() -> list[str]:
    out: list[str] = []
    for path in gap_toast_chrome_e2e_files():
        out.extend(find_agent_stream_violations(path))
    return out
