"""Browser topology cross-file contract (Agent ChromeAgent vs E2E ChromeE2E).

[INPUT]
- Fixed scan targets under open-perplexity monorepo (shell, profile, docs)

[OUTPUT]
- validate_cross_file_contract(): list of violation messages (empty = PASS)
- scan_targets(): resolved (label, path, text) tuples for tests

[POS]
SSOT for ports/forbidden Agent patterns; imported by static SSOT pytest only.
Runtime code continues to use cursor_mcp_isolation.py and api_verify.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from e2e_core.cursor_mcp_isolation import AGENT_CDP_PORT, E2E_CDP_PORT

CANONICAL_AGENT_HINT = (
    f"ChromeAgent :{AGENT_CDP_PORT} "
    "(./myrm doctor --mcp-isolation --strict-live)"
)

FORBIDDEN_AGENT_RECOMMEND_PATTERNS: tuple[str, ...] = (
    "--auto-connect",
    "--autoconnect",
    ":9222",
    "cdmcp-mux-autoconnect",
)

# Allowed when the same line documents prohibition (not a recommendation).
_FORBIDDEN_OK_CONTEXT: tuple[str, ...] = (
    "禁止",
    "forbidden",
    "must not",
    "must not use",
    "steals",
    "AGENT_AUTO_CONNECT",
    "禁 ",
    "禁--",
    "禁`",
    "勿",
    "REFUSED",
    "violations",
    "test_inspect",
)

_AGENT_HINT_MARKERS: tuple[str, ...] = (
    "agent mcp",
    "agent MCP",
    "Agent MCP",
    "chrome-devtools-mcp",
    "vanilla chrome-devtools-mcp",
)

_PROFILE_OPTION_IDS: tuple[str, ...] = (
    "测啥了",
    "提取网址",
)


def _extract_browser_mcp_snippet(profile_text: str) -> str:
    lines = profile_text.splitlines()
    block: list[str] = []
    in_block = False
    for line in lines:
        if line.startswith("  browser-mcp: |"):
            in_block = True
            continue
        if in_block:
            if line.startswith("  ") and not line.startswith("    "):
                break
            if line.strip() and not line.startswith("    "):
                break
            block.append(line)
    return "\n".join(block).strip()


@dataclass(frozen=True, slots=True)
class ScanTarget:
    label: str
    path: Path


def monorepo_root(start: Path | None = None) -> Path:
    """Resolve open-perplexity root from this file location."""
    here = start or Path(__file__).resolve()
    # .../myrm-agent/scripts/dev/lib/e2e_core/browser_topology_contract.py
    return here.parents[5]


def scan_targets(root: Path | None = None) -> tuple[ScanTarget, ...]:
    base = root or monorepo_root()
    return (
        ScanTarget(
            "chrome-e2e-preflight",
            base / "myrm-agent/scripts/dev/chrome-e2e-preflight.sh",
        ),
        ScanTarget("CHROME_MCP_E2E", base / "scripts/dev/CHROME_MCP_E2E.md"),
        ScanTarget(
            "cursor-mcp-isolation-doctor",
            base / "myrm-agent/scripts/dev/cursor-mcp-isolation-doctor.sh",
        ),
        ScanTarget("ifm-profile", base / "ifm/profile.yaml"),
    )


def _extract_profile_option_block(profile_text: str, option_id: str) -> str:
    marker = f"- id: {option_id}"
    start = profile_text.index(marker)
    rest = profile_text[start + len(marker) :]
    next_option = rest.find("\n- id: ")
    return rest if next_option < 0 else rest[:next_option]


def _line_recommends_forbidden_agent_pattern(line: str, pattern: str) -> bool:
    if pattern.lower() not in line.lower():
        return False
    lower = line.lower()
    if any(ctx.lower() in lower for ctx in _FORBIDDEN_OK_CONTEXT):
        return False
    recommend_markers = (
        "should use",
        "must use",
        "use ",
        "应使用",
        "推荐",
        "Agent MCP should",
    )
    if any(marker in line for marker in recommend_markers):
        return True
    # Bare WARN/FAIL echo recommending legacy transport without prohibition context.
    if "CHROME_E2E_WARN" in line or "CHROME_E2E_FAIL" in line:
        return True
    return False


def _line_requires_agent_hint(line: str) -> bool:
    """WARN/FAIL lines that prescribe Agent MCP wiring must cite ChromeAgent :9410."""
    if "Agent MCP should use" in line or "Agent MCP must use" in line:
        lower = line.lower()
        hint_markers = (f":{AGENT_CDP_PORT}", "chromeagent", "mcp-isolation")
        return not any(marker in lower for marker in hint_markers)
    return False


def validate_cross_file_contract(root: Path | None = None) -> list[str]:
    """Return human-readable violations; empty list means PASS."""
    violations: list[str] = []
    for target in scan_targets(root):
        if not target.path.is_file():
            violations.append(f"{target.label}: missing file {target.path}")
            continue
        text = target.path.read_text(encoding="utf-8")

        if target.label == "ifm-profile":
            profile_text = text
            browser_mcp = _extract_browser_mcp_snippet(profile_text)
            if browser_mcp:
                rel = f"{target.path}:browser-mcp"
                for line_no, line in enumerate(browser_mcp.splitlines(), start=1):
                    for pattern in FORBIDDEN_AGENT_RECOMMEND_PATTERNS:
                        if _line_recommends_forbidden_agent_pattern(line, pattern):
                            violations.append(
                                f"{rel}:{line_no}: recommends forbidden Agent pattern "
                                f"{pattern!r}: {line.strip()}"
                            )
            for option_id in _PROFILE_OPTION_IDS:
                block = _extract_profile_option_block(profile_text, option_id)
                rel = f"{target.path}:{option_id}"
                if option_id == "测啥了" and "mux MCP" in block:
                    violations.append(
                        f"{rel}: UI E2E must use ./myrm test -m chrome_e2e, not mux MCP"
                    )
                for line_no, line in enumerate(block.splitlines(), start=1):
                    for pattern in FORBIDDEN_AGENT_RECOMMEND_PATTERNS:
                        if _line_recommends_forbidden_agent_pattern(line, pattern):
                            violations.append(
                                f"{rel}:{line_no}: recommends forbidden Agent pattern "
                                f"{pattern!r}: {line.strip()}"
                            )
            continue

        for line_no, line in enumerate(text.splitlines(), start=1):
            for pattern in FORBIDDEN_AGENT_RECOMMEND_PATTERNS:
                if _line_recommends_forbidden_agent_pattern(line, pattern):
                    violations.append(
                        f"{target.label}:{target.path}:{line_no}: recommends forbidden "
                        f"Agent pattern {pattern!r}: {line.strip()}"
                    )
            if target.label == "chrome-e2e-preflight" and _line_requires_agent_hint(line):
                violations.append(
                    f"{target.label}:{target.path}:{line_no}: Agent MCP hint missing "
                    f":{AGENT_CDP_PORT}/ChromeAgent: {line.strip()}"
                )

        if target.label == "cursor-mcp-isolation-doctor":
            if "auto-connect contract" in text.lower():
                violations.append(
                    f"{target.label}: stale header still references auto-connect contract"
                )

        if target.label == "CHROME_MCP_E2E":
            wrong_role_patterns = (
                rf"ChromeAgent[^\n]{{0,40}}:{E2E_CDP_PORT}\b",
                rf"ChromeE2E[^\n]{{0,40}}:{AGENT_CDP_PORT}\b",
                rf"Agent MCP[^\n]{{0,40}}:{E2E_CDP_PORT}\b",
            )
            for pattern in wrong_role_patterns:
                if re.search(pattern, text, re.IGNORECASE):
                    violations.append(
                        f"{target.label}: port role inversion ({pattern})"
                    )
                    break

    return violations
