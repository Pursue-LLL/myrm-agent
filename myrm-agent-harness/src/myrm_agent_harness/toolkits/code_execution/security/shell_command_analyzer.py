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

Layers 2 to 3c judge every *reading* of the command (below), not only the line as written:

Layer 2 (quote-stripped, BLOCK):
  Injection vectors ($(), backticks, ${}, process substitution), dangerous
  commands (rm -rf /, sudo, fork bombs, etc.), and encoded/inline execution.
  Runs on quote-stripped input so ``echo "rm -rf /"`` won't false-positive.
  ``;`` chains commands like ``&&`` does and is no threat of its own.

Layer 2.5 (ORIGINAL reading, ESCALATE):
  SQL statement guard — detects destructive SQL in DB client commands
  (psql/mysql/sqlite3/sqlcmd/mongosh). Runs on the reading before
  quote stripping to catch SQL inside single quotes.
  See: sql_statement_guard.py

Layer 3 (quote-stripped, ESCALATE):
  Suspicious but potentially legitimate patterns (curl|sh, eval, base64 -d,
  kill/pkill/killall). Forces ASK regardless of permission ruleset.

Layer 3c (ORIGINAL reading, ESCALATE):
  A write to a protected instruction file (redirect, ``sed -i``, ``tee``, ``cp``, ``mv``, ``rm``, ``truncate``, their
  PowerShell and cmd spellings, an interpreter opening it for writing), read command by command; the evidence is the
  file name.
  See: protected_instruction_command.py

Readings (``shell_command_readings.command_readings``):
  The line as written, every command line the line hands to a shell (the script of ``sh -c`` / ``eval``, a ``trap``
  handler, the body of a ``$(...)`` or backtick substitution) and each command of it apart. A rule written for
  ``rm -rf ~`` therefore fires on ``rm -rf ~&&echo``, ``eval "rm -rf ~"`` and ``trap 'rm -rf ~' EXIT`` as on the bare
  command. A command behind ``sudo``, ``env`` or ``timeout`` is judged where it stands, with its quotes: the rules
  match a command wherever it stands in the text, and the quoted text of its arguments stays masked. A line the
  readings cannot hold (too many scripts and substitutions, too much text) is refused (BLOCK, category
  ``obfuscation``), because a payload may sit in the part left unread.

Consumers:
- execution/security/validator.validate_command() — defense-in-depth check
- agent/security/engine.evaluate_tool_call() — primary check
- toolkits/cron/runners.ShellJobRunner — pre-execution check

[INPUT]
- security.shell_command_readings::command_readings, UNREAD_EVIDENCE (POS: The texts the rule tables are matched against, bounded; says when a line does not fit them)
- security.protected_instruction_command::protected_instruction_mutation_target (POS: The shell-side reading of the protected instruction files, shared with the permission engine and the allow-always guard)
- security.shell_command_rules (POS: Pattern catalogue for layers 1-3 and the snapshot trigger; this module holds the engine)
- security.shell_command_strip::_strip_quoted_content (POS: Quote-stripping helper for shell command preprocessing)

[OUTPUT]
- ThreatLevel: Severity level of a detected command threat.
- CommandThreat: A single security threat detected in a shell command.
- PROTECTED_WRITE_CATEGORY: The threat category of a write to a protected instruction file.
- analyze_hidden_characters: Layer 1 alone (control and invisible characters), valid for shell and Python text.
- analyze_command: Analyze a shell command for security threats.
- has_block_threat: Quick check: return the first BLOCK-level threat, or None if clean.
- has_escalate_threat: Quick check: return the first ESCALATE-level threat, or None if clean.
- is_destructive_command: Whether any reading of a command changes files or repository state (snapshot trigger).
- is_integration_mutation_command: Whether any reading of a command writes to a third-party integration.

[POS]
Shell Command Analyzer — unified security analysis for shell commands.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .protected_instruction_command import protected_instruction_mutation_target
from .shell_command_readings import UNREAD_EVIDENCE, command_readings
from .shell_command_rules import (
    ANSI_C_QUOTE_RE,
    BINARY_INJECTION,
    DANGEROUS_COMMANDS_COMPILED,
    DESTRUCTIVE_COMMANDS_COMPILED,
    INJECTION_VECTORS_COMPILED,
    INVISIBLE_UNICODE,
    LOCALE_QUOTE_RE,
    SUSPICIOUS_PATTERNS_COMPILED,
)
from .shell_command_strip import _strip_quoted_content


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


def _normalized(text: str) -> str:
    """The text the pattern tables are matched on: single-quoted content masked, blanks collapsed."""
    return " ".join(_strip_quoted_content(text).split())


def is_destructive_command(command: str) -> bool:
    """Check if a command is destructive (modifies files/state significantly).

    This is used to trigger auto-snapshots before execution. A command a wrapper runs counts as the command itself.
    """
    if not command or not command.strip():
        return False
    return any(
        any(pattern.search(normalized) for pattern in DESTRUCTIVE_COMMANDS_COMPILED)
        for normalized in map(_normalized, command_readings(command).texts)
    )


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


def _quoting_evasion_threats(command: str) -> list[CommandThreat]:
    """Layer 1.5: ANSI-C and locale quoting, which hide a command behind escape sequences."""
    threats: list[CommandThreat] = []
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
    return threats


# A line the readings cannot hold hides what runs in the part left unread.
_UNREAD_THREAT: Final = CommandThreat(
    level=ThreatLevel.BLOCK,
    category="obfuscation",
    detail="The command holds more scripts, substitutions or text than can be read in full; run it as separate commands",
    evidence=UNREAD_EVIDENCE,
)


def _table_threats(
    normalized: str,
    table: tuple[tuple[re.Pattern[str], str], ...],
    level: ThreatLevel,
    category: str,
) -> list[CommandThreat]:
    """The threats of every pattern of *table* that matches the normalized text."""
    return [
        CommandThreat(level, category, desc, match.group(0))
        for pattern, desc in table
        if (match := pattern.search(normalized))
    ]


def _reading_threats(text: str) -> list[CommandThreat]:
    """Layers 2 to 3c for one reading of a command."""
    from myrm_agent_harness.toolkits.code_execution.security.sql_statement_guard import check_sql_threats

    normalized = _normalized(text)
    threats = _table_threats(normalized, INJECTION_VECTORS_COMPILED, ThreatLevel.BLOCK, "injection")
    threats += _table_threats(normalized, DANGEROUS_COMMANDS_COMPILED, ThreatLevel.BLOCK, "dangerous_command")
    # Layer 2.5 reads the text before quote stripping: the SQL sits inside single quotes.
    threats += check_sql_threats(text)
    threats += _table_threats(normalized, SUSPICIOUS_PATTERNS_COMPILED, ThreatLevel.ESCALATE, "suspicious_pattern")
    threats += _table_threats(
        normalized, _integration_write_patterns_compiled(), ThreatLevel.ESCALATE, "integration_mutation"
    )

    protected_file = protected_instruction_mutation_target(text)
    if protected_file is not None:
        threats.append(
            CommandThreat(
                level=ThreatLevel.ESCALATE,
                category=PROTECTED_WRITE_CATEGORY,
                detail="Attempted modification of protected instruction file via shell command",
                evidence=protected_file,
            )
        )
    return threats


def analyze_command(command: str) -> tuple[CommandThreat, ...]:
    """Analyze a shell command for security threats.

    Returns all detected threats sorted by severity (BLOCK first, then ESCALATE).
    Pure function — no side effects, no I/O.

    Layers 1 and 1.5 (binary/Unicode, quoting evasion) check the raw string. Layers 2 to 3c check every reading of
    the command: the line as written, each command of it apart, and each command a wrapper (``bash -c '...'``,
    ``eval``, ``sudo``, ``$(...)``, ``trap '...'``) hands control to. The line as written is read first, so the
    threat it carries is reported before the one a wrapper hides, and a threat several readings share is reported once.
    A line the readings cannot hold is refused, because a payload may sit in the part left unread.
    """
    if not command or not command.strip():
        return ()

    threats = [*analyze_hidden_characters(command), *_quoting_evasion_threats(command)]
    readings = command_readings(command)
    for reading in readings.texts:
        threats.extend(_reading_threats(reading))
    if not readings.complete:
        threats.append(_UNREAD_THREAT)
    return tuple(sorted(dict.fromkeys(threats), key=lambda threat: threat.level is not ThreatLevel.BLOCK))


def is_integration_mutation_command(command: str) -> bool:
    """Return True when a shell command, or a command a wrapper runs, performs a third-party integration write."""
    patterns = _integration_write_patterns_compiled()
    if not patterns:
        return False
    return any(
        pattern.search(normalized)
        for normalized in map(_normalized, command_readings(command).texts)
        for pattern, _desc in patterns
    )


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
