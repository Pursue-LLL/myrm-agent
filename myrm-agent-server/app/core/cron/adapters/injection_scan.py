"""Prompt injection scanning for cron job prompts.

Scans assembled cron prompts against the harness skill scanner's
PROMPT_INJECTION_PATTERNS (12 patterns: instruction override,
identity reassignment, system prompt manipulation, etc.).

[INPUT]
- myrm_agent_harness.backends.skills.scanning.patterns::PROMPT_INJECTION_PATTERNS (POS: 12 injection patterns)

[OUTPUT]
- scan_cron_prompt: scan function returning threat descriptions

[POS]
Server-layer cron prompt injection scanner. Reuses harness pattern library.
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS: list[tuple[re.Pattern[str], str]] | None = None


def _get_injection_patterns() -> list[tuple[re.Pattern[str], str]]:
    """Lazy-load prompt injection patterns from the harness skill scanner."""
    global _INJECTION_PATTERNS
    if _INJECTION_PATTERNS is not None:
        return _INJECTION_PATTERNS

    from myrm_agent_harness.backends.skills.scanning.patterns import PROMPT_INJECTION_PATTERNS

    _INJECTION_PATTERNS = [(p, d) for p, d, _ in PROMPT_INJECTION_PATTERNS]
    return _INJECTION_PATTERNS


def scan_cron_prompt(prompt: str) -> list[str]:
    """Scan a cron prompt for injection patterns.

    Returns a list of threat descriptions. Empty list means clean.
    """
    if not prompt or not prompt.strip():
        return []

    findings: list[str] = []
    patterns = _get_injection_patterns()

    for line in prompt.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for pattern, description in patterns:
            if pattern.search(stripped):
                findings.append(description)

    return findings
