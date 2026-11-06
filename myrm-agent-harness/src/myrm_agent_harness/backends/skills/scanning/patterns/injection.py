"""技能安全扫描模式：injection 类。

[POS]
patterns 子包的一部分；纯数据，由 __init__.py 汇总。
"""

from __future__ import annotations

import re

from ..scanner import ScanSeverity
from .types import PatternList

PROMPT_INJECTION_PATTERNS: PatternList = [
    (
        re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|rules?|prompts?)", re.IGNORECASE),
        "Prompt injection: instruction override attempt",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"you\s+are\s+now\s+(a|an|the)\s+", re.IGNORECASE),
        "Prompt injection: identity reassignment attempt",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"(system\s*prompt|system\s*message)\s*[:=]", re.IGNORECASE),
        "Prompt injection: system prompt manipulation",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"do\s+not\s+(follow|obey|listen)\s+(to\s+)?(the\s+)?(user|human|instructions?)", re.IGNORECASE),
        "Prompt injection: instruction disobedience directive",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"<\s*/?\s*(?:system|assistant|user)\s*>", re.IGNORECASE),
        "Prompt injection: role boundary tag injection",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"do\s+not\s+(?:\w+\s+)*tell\s+(?:\w+\s+)*the\s+user", re.IGNORECASE),
        "Prompt injection: deception — hide information from user",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\bDAN\s+mode\b|Do\s+Anything\s+Now", re.IGNORECASE),
        "Prompt injection: DAN jailbreak attempt",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\bdeveloper\s+mode\b.*\benabled?\b", re.IGNORECASE),
        "Prompt injection: developer mode jailbreak",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"hypothetical\s+scenario.*(?:ignore|bypass|override)", re.IGNORECASE),
        "Prompt injection: hypothetical scenario bypass",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(
            r"(respond|answer|reply)\s+without\s+(?:\w+\s+)*(restrictions|limitations|filters|safety)", re.IGNORECASE
        ),
        "Prompt injection: remove safety filters",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"<!--[^>]*(?:ignore|override|system|secret|hidden)[^>]*-->", re.IGNORECASE),
        "Prompt injection: hidden instructions in HTML comments",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"<\s*div\s+style\s*=\s*[\"'].*display\s*:\s*none", re.IGNORECASE),
        "Prompt injection: hidden HTML div with invisible instructions",
        ScanSeverity.HIGH,
    ),
]

COMMAND_INJECTION_PATTERNS: PatternList = [
    (
        re.compile(r"(?:rm|del)\s+-[rf]+\s+/", re.IGNORECASE),
        "Command injection: recursive delete on root path",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"curl\s+.*\|\s*(?:bash|sh|zsh)", re.IGNORECASE),
        "Command injection: remote script execution via pipe",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"wget\s+.*-O\s*-\s*\|\s*(?:bash|sh)", re.IGNORECASE),
        "Command injection: remote script execution via wget pipe",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"eval\s*\(\s*['\"].*['\"]", re.IGNORECASE),
        "Command injection: eval with string argument",
        ScanSeverity.MEDIUM,
    ),
]

CODE_INJECTION_PATTERNS: PatternList = [
    (
        re.compile(r"\bexec\s*\(", re.IGNORECASE),
        "Code injection: exec() call",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bcompile\s*\(\s*['\"]", re.IGNORECASE),
        "Code injection: compile() with string source",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"\b__import__\s*\(", re.IGNORECASE),
        "Code injection: dynamic import via __import__",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bimportlib\.import_module\s*\(", re.IGNORECASE),
        "Code injection: dynamic import via importlib",
        ScanSeverity.MEDIUM,
    ),
]
