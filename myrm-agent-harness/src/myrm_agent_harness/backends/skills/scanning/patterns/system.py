"""[INPUT]
- myrm_agent_harness.backends.skills.scanning.scanner::ScanSeverity (POS: myrm_agent_harness.backends.skills.scanning.scanner)
- myrm_agent_harness.backends.skills.scanning.patterns.types::PatternList (POS: patterns 子包共用类型；避免每个模式模块重复导入 scanner。)

[OUTPUT]
- （仅导出常量/类型）

[POS]
patterns 子包的一部分；纯数据，由 __init__.py 汇总。
"""

from __future__ import annotations

import re

from ..scanner import ScanSeverity
from .types import PatternList

SCREEN_INPUT_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:screenshot|screen_capture|keylog|keyboard\.record|mouse\.record)\b", re.IGNORECASE),
        "Screen/Input: screen capture or input recording",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\b(?:clipboard\.get|pyperclip\.paste|pbpaste)\b", re.IGNORECASE),
        "Screen/Input: clipboard access",
        ScanSeverity.MEDIUM,
    ),
]

MEMORY_CONFIG_PATTERNS: PatternList = [
    (
        re.compile(r"(?:read|cat|open|access|head|tail)\s+.*(?:MEMORY\.md|memory\.json)", re.IGNORECASE),
        "Memory snooping: access to agent memory files",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"(?:read|cat|open|access|head|tail|ls)\s+.*(?:\.claude/|\.cursor/|\.vscode/)", re.IGNORECASE),
        "Config snooping: access to IDE/agent configuration directories",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"(?:read|cat|open|access)\s+.*(?:~/\.config/|~/\.local/|~/\.gnupg/)", re.IGNORECASE),
        "Config snooping: access to user configuration directories",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(
            r"(?:read|cat|open|access)\s+.*(?:settings\.json|keybindings\.json|mcp\.json)",
            re.IGNORECASE,
        ),
        "Config snooping: access to IDE settings files",
        ScanSeverity.MEDIUM,
    ),
]

PRIVILEGE_ESCALATION_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:chmod|chown)\s+.*(?:777|666|\+s)", re.IGNORECASE),
        "Privilege escalation: dangerous permission change",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\b(?:setuid|setgid|seteuid|setegid)\b", re.IGNORECASE),
        "Privilege escalation: UID/GID manipulation",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\bsudo\s+", re.IGNORECASE),
        "Privilege escalation: sudo usage",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bNOPASSWD\b", re.IGNORECASE),
        "Privilege escalation: NOPASSWD sudoers entry",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\bchmod\s+[u+]?s\b", re.IGNORECASE),
        "Privilege escalation: SUID/SGID bit set",
        ScanSeverity.CRITICAL,
    ),
]

ENVIRONMENT_MANIPULATION_PATTERNS: PatternList = [
    (
        re.compile(r"\bos\.environ\s*\[.*\]\s*=", re.IGNORECASE),
        "Environment manipulation: direct os.environ modification",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"\b(?:dotenv|load_dotenv)\b", re.IGNORECASE),
        "Environment manipulation: dotenv loading",
        ScanSeverity.LOW,
    ),
    (
        re.compile(r"\bos\.putenv\s*\(", re.IGNORECASE),
        "Environment manipulation: os.putenv call",
        ScanSeverity.MEDIUM,
    ),
]

REFLECTION_PATTERNS: PatternList = [
    (
        re.compile(r"\b__subclasses__\s*\(\s*\)", re.IGNORECASE),
        "Reflection: class hierarchy traversal (__subclasses__)",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\b__globals__\b", re.IGNORECASE),
        "Reflection: globals access (__globals__)",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\b__builtins__\b", re.IGNORECASE),
        "Reflection: builtins access (__builtins__)",
        ScanSeverity.HIGH,
    ),
]

DESERIALIZATION_PATTERNS: PatternList = [
    (
        re.compile(r"\bpickle\.loads?\s*\(", re.IGNORECASE),
        "Deserialization: pickle.load (arbitrary code execution risk)",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\byaml\.(?:load|unsafe_load)\s*\(", re.IGNORECASE),
        "Deserialization: yaml.load without safe_load",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bmarshal\.loads?\s*\(", re.IGNORECASE),
        "Deserialization: marshal.load (code object injection)",
        ScanSeverity.CRITICAL,
    ),
]

LOG_AUDIT_TAMPERING_PATTERNS: PatternList = [
    (
        re.compile(r"\blogging\.disable\s*\(", re.IGNORECASE),
        "Log tampering: logging.disable call",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\blogger\.setLevel\s*\(\s*(?:100|logging\.CRITICAL\s*\+)", re.IGNORECASE),
        "Log tampering: setting log level to suppress output",
        ScanSeverity.HIGH,
    ),
]

SCHEDULED_TASK_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:crontab|at\s+-f|systemctl\s+enable)\b", re.IGNORECASE),
        "Scheduled task injection: system scheduler manipulation",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\blaunchctl\s+(?:load|submit)\b", re.IGNORECASE),
        "Scheduled task injection: macOS launchctl manipulation",
        ScanSeverity.HIGH,
    ),
]

MEMORY_MANIPULATION_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:ctypes\.CDLL|ctypes\.windll|ctypes\.cdll)\b", re.IGNORECASE),
        "Memory manipulation: ctypes foreign function interface",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bmmap\.mmap\s*\(", re.IGNORECASE),
        "Memory manipulation: memory-mapped file access",
        ScanSeverity.MEDIUM,
    ),
]

SUPPLY_CHAIN_PATTERNS: PatternList = [
    (
        re.compile(r"\bpip\s+install\s+.*--index-url\s+(?!https://pypi\.org)", re.IGNORECASE),
        "Supply chain: pip install from non-standard index",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bnpm\s+install\s+.*--registry\s+(?!https://registry\.npmjs\.org)", re.IGNORECASE),
        "Supply chain: npm install from non-standard registry",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bsetup\.py\b.*\binstall\b", re.IGNORECASE),
        "Supply chain: setup.py install execution",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"\bpip\s+install\s+(?!-r\s)(?!.*==)\S+", re.IGNORECASE),
        "Supply chain: pip install without version pinning",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"(?:curl|wget|httpx?\.get|requests\.get|fetch)\s*[\(]?\s*[\"']https?://", re.IGNORECASE),
        "Supply chain: fetches remote resource at runtime",
        ScanSeverity.MEDIUM,
    ),
]

OBFUSCATION_PATTERNS: PatternList = [
    (
        re.compile(r"\bbase64\.b64decode\s*\(.*\)\s*\)\s*$", re.IGNORECASE),
        "Obfuscation: base64 decode at end of expression (likely exec)",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bexec\s*\(\s*(?:base64|codecs|bytes\.fromhex)", re.IGNORECASE),
        "Obfuscation: exec with encoded payload",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\\x[0-9a-fA-F]{2}(?:\\x[0-9a-fA-F]{2}){10,}", re.IGNORECASE),
        "Obfuscation: long hex-escaped byte sequence",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bchr\s*\(\s*\d+\s*\)\s*\+\s*chr\s*\(\s*\d+\s*\)", re.IGNORECASE),
        "Obfuscation: string construction via chr() concatenation",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"echo\s+[^\n]*\|\s*(?:bash|sh|python|perl|ruby|node)", re.IGNORECASE),
        "Obfuscation: echo piped to interpreter for execution",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"compile\s*\(\s*[^\)]+,\s*[\"'].*[\"']\s*,\s*[\"']exec[\"']\s*\)", re.IGNORECASE),
        "Obfuscation: compile() with exec mode",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\[::-1\]"),
        "Obfuscation: string reversal (possible obfuscated payload)",
        ScanSeverity.LOW,
    ),
]
