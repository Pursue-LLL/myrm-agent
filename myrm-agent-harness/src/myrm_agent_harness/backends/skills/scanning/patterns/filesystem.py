"""技能安全扫描模式：filesystem 类。

[POS]
patterns 子包的一部分；纯数据，由 __init__.py 汇总。
"""

from __future__ import annotations

import re

from ..scanner import ScanSeverity
from .types import PatternList

FILESYSTEM_PATTERNS: PatternList = [
    (
        re.compile(r"(?:read|write|open|access)\s+.*(?:/etc/passwd|/etc/shadow|\.ssh/)", re.IGNORECASE),
        "File system: access to sensitive system files",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"(?:read|cat|head|tail)\s+.*(?:\.env|\.pem|\.key|credentials)", re.IGNORECASE),
        "File system: access to credential files",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"Path[^\n]*[\"'](?:[^\"']*/)?\.(?:ssh|aws|kube|docker|gnupg)[/\"']", re.IGNORECASE),
        "File system: pathlib access to sensitive credential directory",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"/var/run/secrets/|/run/secrets/", re.IGNORECASE),
        "File system: container-mounted secrets path (K8s/Docker)",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"serviceaccount/token|kubernetes\.io/serviceaccount", re.IGNORECASE),
        "File system: Kubernetes service account token path",
        ScanSeverity.HIGH,
    ),
]

PROCESS_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:subprocess|os\.system|os\.exec|os\.spawn|Popen)\b", re.IGNORECASE),
        "Process: direct process execution API usage",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"\b(?:kill|pkill|killall)\s+-\d+\s+", re.IGNORECASE),
        "Process: process termination command",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bos\.popen\s*\(", re.IGNORECASE),
        "Process: os.popen shell pipe execution",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"`[^`]*\$\([^)]+\)[^`]*`", re.IGNORECASE),
        "Process: backtick string with command substitution",
        ScanSeverity.MEDIUM,
    ),
]

DESTRUCTIVE_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:mkfs|fdisk|dd\s+if=.*of=/dev/)", re.IGNORECASE),
        "Destructive: disk formatting or raw device write",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\b(?:shutil\.rmtree|os\.removedirs)\s*\(\s*['\"/]", re.IGNORECASE),
        "Destructive: recursive directory removal from root-like path",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\btruncate\s+.*--size\s+0\b", re.IGNORECASE),
        "Destructive: file truncation to zero",
        ScanSeverity.HIGH,
    ),
]

PERSISTENCE_PATTERNS: PatternList = [
    (
        re.compile(r"(?:>>?\s*)?~/?\.\b(?:bashrc|zshrc|profile|bash_profile|zprofile)\b", re.IGNORECASE),
        "Persistence: shell startup file modification",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\b(?:autostart|startup|init\.d|rc\.local)\b.*(?:write|append|>>)", re.IGNORECASE),
        "Persistence: system startup script injection",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"~/\.(?:ssh/authorized_keys|ssh/config)\b", re.IGNORECASE),
        "Persistence: SSH configuration modification",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\b(?:AGENTS\.md|CLAUDE\.md|\.cursorrules|\.clinerules)\b", re.IGNORECASE),
        "Persistence: agent config file modification (cross-session injection)",
        ScanSeverity.CRITICAL,
    ),
]

PATH_TRAVERSAL_PATTERNS: PatternList = [
    (
        re.compile(r"\.\./\.\./\.\.", re.IGNORECASE),
        "Path traversal: deep relative traversal (3+ levels up)",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"/proc/self|/proc/\d+/", re.IGNORECASE),
        "Path traversal: /proc filesystem process introspection",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"/dev/shm/", re.IGNORECASE),
        "Path traversal: shared memory access (common staging area)",
        ScanSeverity.MEDIUM,
    ),
]
