"""Shell Command Analyzer — unified security analysis for shell commands.

Multi-layer detection with quote-aware preprocessing:

Layer 1 (raw string, always checked; ``analyze_hidden_characters``):
  Binary injection (embedded newlines, null bytes) and invisible Unicode
  obfuscation (12 categories). Never legitimate in LLM-generated commands, in a
  shell line or in Python source.

Layer 1.5 (raw string, BLOCK, shell text only):
  ANSI-C quoting ($'...') and locale quoting ($"...") that can hide arbitrary
  commands via escape sequences (hex, unicode, octal). Always obfuscation in a
  command line a shell reads; in Python source ``$'`` is a regex end anchor next
  to a quote, so callers that know the text is Python skip this layer.

Layer 2 (quote-stripped, BLOCK):
  Injection vectors ($(), backticks, ${}, etc.), dangerous commands
  (rm -rf /, sudo, fork bombs, etc.), and encoded/inline execution.
  Runs on quote-stripped input so ``echo "rm -rf /"`` won't false-positive.
  Includes ``find -exec {} \\;`` exemption for the escaped semicolon.

Layer 2.5 (ORIGINAL command, ESCALATE):
  SQL statement guard — detects destructive SQL in DB client commands
  (psql/mysql/sqlite3/sqlcmd/mongosh). Runs on the original command before
  quote stripping to catch SQL inside single quotes.
  See: sql_statement_guard.py

Layer 3 (quote-stripped, ESCALATE):
  Suspicious but potentially legitimate patterns (curl|sh, eval, base64 -d,
  kill/pkill/killall). Forces ASK regardless of permission ruleset.

Layer 3c (ORIGINAL command, ESCALATE):
  A write to a protected instruction file (redirect, ``sed -i``, ``tee``, ``cp``, ``mv``, ``rm``, ``truncate``, their
  PowerShell and cmd spellings, an interpreter opening it for writing), read command by command; the evidence is the
  file name.
  See: protected_instruction_command.py

Layer 4 (recursive, BLOCK/ESCALATE):
  Extracts commands from shell wrappers that hide payloads in single quotes
  (bash -c '...', sh -c '...', trap '...' SIGNAL) and recursively analyzes
  them. Depth-limited to prevent DoS.

Consumers:
- execution/security/validator.validate_command() — defense-in-depth check
- agent/security/engine.evaluate_tool_call() — primary check
- toolkits/cron/runners.ShellJobRunner — pre-execution check

[INPUT]
- security.protected_instruction_command::protected_instruction_mutation_target (POS: The shell-side reading of the protected instruction files, shared with the permission engine and the allow-always guard)
- security.shell_command_rules (POS: Pattern catalogue for layers 1-3; this module holds the engine)

[OUTPUT]
- ThreatLevel: Severity level of a detected command threat.
- CommandThreat: A single security threat detected in a shell command.
- PROTECTED_WRITE_CATEGORY: The threat category of a write to a protected instruction file.
- analyze_hidden_characters: Layer 1 alone (control and invisible characters), valid for shell and Python text.
- analyze_command: Analyze a shell command for security threats.
- has_block_threat: Quick check: return the first BLOCK-level threat, or None if clean.
- has_escalate_threat: Quick check: return the first ESCALATE-level threat, or None if clean.

[POS]
Shell Command Analyzer — unified security analysis for shell commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .protected_instruction_command import protected_instruction_mutation_target
from .shell_command_rules import (
    ANSI_C_QUOTE_RE,
    BINARY_INJECTION,
    DANGEROUS_COMMANDS_COMPILED,
    FIND_EXEC_TERMINATOR_RE,
    INJECTION_VECTORS_COMPILED,
    INVISIBLE_UNICODE,
    LOCALE_QUOTE_RE,
    SUSPICIOUS_PATTERNS_COMPILED,
)


class ThreatLevel(StrEnum):
    """Severity level of a detected command threat."""

    BLOCK = "block"
    ESCALATE = "escalate"


@dataclass(frozen=True, slots=True)
class CommandThreat:
    """A single security threat detected in a shell command."""

    level: ThreatLevel
    category: str
    detail: str
    evidence: str


# The category of the escalation for a write to a protected instruction file: the permission engine words its ask
# from it, with the file name the threat carries as evidence.
PROTECTED_WRITE_CATEGORY: Final = "protected_instruction_mutation"


# ---------------------------------------------------------------------------
# Layer 3b: ESCALATE — third-party integration write mutations (quote-stripped)
# Registered at runtime by the business layer via register_integration_write_patterns().
# ---------------------------------------------------------------------------

_EXTRA_INTEGRATION_WRITE_PATTERNS: list[tuple[re.Pattern[str], str]] = []


def register_integration_write_patterns(patterns: tuple[tuple[str, str], ...]) -> None:
    """Register business-layer integration write-detection regex patterns.

    Harness ships with zero vendor-specific rules; myrm-agent-server registers
    patterns (e.g. Google Workspace) at startup. Duplicate pattern strings are ignored.
    """
    existing = {compiled.pattern for compiled, _ in _EXTRA_INTEGRATION_WRITE_PATTERNS}
    for pattern, desc in patterns:
        compiled = re.compile(pattern, re.IGNORECASE)
        if compiled.pattern in existing:
            continue
        _EXTRA_INTEGRATION_WRITE_PATTERNS.append((compiled, desc))
        existing.add(compiled.pattern)


def _integration_write_patterns_compiled() -> tuple[tuple[re.Pattern[str], str], ...]:
    return tuple(_EXTRA_INTEGRATION_WRITE_PATTERNS)


# ---------------------------------------------------------------------------
# Quote-aware preprocessing & recursive shell wrapper analysis
# ---------------------------------------------------------------------------

from .shell_command_strip import _strip_quoted_content  # noqa: E402

_MAX_RECURSIVE_DEPTH = 8

_SHELL_EXEC_SINGLE_QUOTE_RE = re.compile(r"\b(?:ba|da|z|k)?sh\s+-[a-zA-Z]*c\s+'([^']+)'")
_TRAP_SINGLE_QUOTE_RE = re.compile(r"\btrap\s+'([^']+)'\s+\w+")


def _extract_embedded_commands(command: str) -> list[str]:
    """Extract commands hidden inside single-quoted shell wrappers."""
    embedded: list[str] = []
    for match in _SHELL_EXEC_SINGLE_QUOTE_RE.finditer(command):
        embedded.append(match.group(1))
    for match in _TRAP_SINGLE_QUOTE_RE.finditer(command):
        embedded.append(match.group(1))
    return embedded


def _analyze_recursive(command: str, depth: int) -> list[CommandThreat]:
    """Recursively analyze embedded commands up to MAX_RECURSIVE_DEPTH."""
    if depth >= _MAX_RECURSIVE_DEPTH:
        return []

    embedded = _extract_embedded_commands(command)
    threats: list[CommandThreat] = []
    for cmd in embedded:
        threats.extend(analyze_command(cmd, _depth=depth + 1))
    return threats


def is_destructive_command(command: str) -> bool:
    """Check if a command is destructive (modifies files/state significantly).

    This is used to trigger auto-snapshots before execution.
    """
    if not command or not command.strip():
        return False

    stripped = _strip_quoted_content(command)
    normalized = " ".join(stripped.split())

    # Common destructive commands
    destructive_patterns = [
        r"\brm\s+",
        r"\bmv\s+",
        r"\bsed\s+-i\b",
        r"\bgit\b(?:\s+\S+)*?\s+(reset|clean|checkout|restore|apply)(?=\s|$)",
        r"\bcp\s+.*-r\b",
        r"\bfind\s+.*-delete\b",
        r"\bfind\s+.*-exec\s+rm\b",
        r">\s*\S+",  # Redirection overwrite
    ]

    return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in destructive_patterns)


def analyze_hidden_characters(text: str) -> tuple[CommandThreat, ...]:
    """Layer 1: control and invisible characters that hide what a command or a script does.

    Language-independent, so it also judges Python source the bash tool runs without a shell.
    """
    threats = [
        CommandThreat(ThreatLevel.BLOCK, "binary_injection", desc, repr(char))
        for char, desc in BINARY_INJECTION
        if char in text
    ]
    threats += [
        CommandThreat(ThreatLevel.BLOCK, "obfuscation", f"Invisible Unicode character: {desc}", repr(char))
        for char, desc in INVISIBLE_UNICODE
        if char in text
    ]
    return tuple(threats)


def analyze_command(command: str, *, _depth: int = 0) -> tuple[CommandThreat, ...]:
    """Analyze a shell command for security threats.

    Returns all detected threats sorted by severity (BLOCK first, then ESCALATE).
    Pure function — no side effects, no I/O.

    Layer 1 (binary/Unicode) checks run on the raw string.
    Layer 2/3 (injection vectors, dangerous commands, suspicious patterns) run
    on the quote-stripped string so ``echo "rm -rf /"`` won't false-positive.
    Layer 4 (recursive) extracts commands from `bash -c '...'` and `trap '...'`
    wrappers and recursively analyzes them.
    """
    if not command or not command.strip():
        return ()

    threats: list[CommandThreat] = list(analyze_hidden_characters(command))

    # Layer 1.5: ANSI-C / locale quoting detection (before quote stripping)
    ansi_c_match = ANSI_C_QUOTE_RE.search(command)
    if ansi_c_match:
        threats.append(
            CommandThreat(
                level=ThreatLevel.BLOCK,
                category="obfuscation",
                detail="ANSI-C quoting ($'...') can hide arbitrary commands via escape sequences",
                evidence=ansi_c_match.group(0),
            )
        )

    locale_match = LOCALE_QUOTE_RE.search(command)
    if locale_match:
        threats.append(
            CommandThreat(
                level=ThreatLevel.BLOCK,
                category="obfuscation",
                detail='Locale quoting ($"...") can hide characters via escape sequences',
                evidence=locale_match.group(0),
            )
        )

    stripped = _strip_quoted_content(command)
    normalized = " ".join(stripped.split())

    for pattern, desc in INJECTION_VECTORS_COMPILED:
        match = pattern.search(normalized)
        if match:
            if desc == "semicolon command chaining" and FIND_EXEC_TERMINATOR_RE.search(normalized):
                continue
            detail_msg = desc
            if desc == "semicolon command chaining":
                detail_msg = "semicolon command chaining (';' is forbidden; use '&&' or separate lines/calls)"
            threats.append(
                CommandThreat(
                    level=ThreatLevel.BLOCK,
                    category="injection",
                    detail=detail_msg,
                    evidence=match.group(0),
                )
            )

    for pattern, desc in DANGEROUS_COMMANDS_COMPILED:
        match = pattern.search(normalized)
        if match:
            threats.append(
                CommandThreat(
                    level=ThreatLevel.BLOCK,
                    category="dangerous_command",
                    detail=desc,
                    evidence=match.group(0),
                )
            )

    # Layer 2.5: SQL statement guard (uses ORIGINAL command for DB client extraction)
    from myrm_agent_harness.toolkits.code_execution.security.sql_statement_guard import (
        check_sql_threats,
    )

    threats.extend(check_sql_threats(command))

    for pattern, desc in SUSPICIOUS_PATTERNS_COMPILED:
        match = pattern.search(normalized)
        if match:
            threats.append(
                CommandThreat(
                    level=ThreatLevel.ESCALATE,
                    category="suspicious_pattern",
                    detail=desc,
                    evidence=match.group(0),
                )
            )

    for pattern, desc in _integration_write_patterns_compiled():
        match = pattern.search(normalized)
        if match:
            threats.append(
                CommandThreat(
                    level=ThreatLevel.ESCALATE,
                    category="integration_mutation",
                    detail=desc,
                    evidence=match.group(0),
                )
            )

    protected_file = protected_instruction_mutation_target(command)
    if protected_file is not None:
        threats.append(
            CommandThreat(
                level=ThreatLevel.ESCALATE,
                category=PROTECTED_WRITE_CATEGORY,
                detail="Attempted modification of protected instruction file via shell command",
                evidence=protected_file,
            )
        )

    # Layer 4: Recursive analysis of embedded commands in shell wrappers
    if _depth < _MAX_RECURSIVE_DEPTH:
        threats.extend(_analyze_recursive(command, _depth))

    threats.sort(key=lambda t: 0 if t.level == ThreatLevel.BLOCK else 1)
    return tuple(threats)


def is_integration_mutation_command(command: str) -> bool:
    """Return True when a shell command performs a third-party integration write."""
    stripped = _strip_quoted_content(command)
    normalized = " ".join(stripped.split())
    return any(pattern.search(normalized) for pattern, _desc in _integration_write_patterns_compiled())


def has_block_threat(command: str) -> CommandThreat | None:
    """Quick check: return the first BLOCK-level threat, or None if clean."""
    for threat in analyze_command(command):
        if threat.level == ThreatLevel.BLOCK:
            return threat
    return None


def has_escalate_threat(command: str) -> CommandThreat | None:
    """Quick check: return the first ESCALATE-level threat, or None if clean."""
    for threat in analyze_command(command):
        if threat.level == ThreatLevel.ESCALATE:
            return threat
    return None
