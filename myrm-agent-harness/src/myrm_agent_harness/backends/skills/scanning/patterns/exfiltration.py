"""技能安全扫描模式：exfiltration 类。

[POS]
patterns 子包的一部分；纯数据，由 __init__.py 汇总。
"""

from __future__ import annotations

import re

from ..scanner import ScanSeverity
from .types import PatternList

CREDENTIAL_PATTERNS: PatternList = [
    (
        re.compile(
            r"(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token)\s*[:=]\s*['\"][A-Za-z0-9+/=_-]{20,}['\"]",
            re.IGNORECASE,
        ),
        "Credential exposure: hardcoded API key or token",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"(?:password|passwd|pwd)\s*[:=]\s*['\"][^'\"]{8,}['\"]", re.IGNORECASE),
        "Credential exposure: hardcoded password",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----"),
        "Credential exposure: embedded private key",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"ghp_[A-Za-z0-9]{36}|github_pat_[A-Za-z0-9_]{80,}"),
        "Credential exposure: GitHub personal access token",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"sk-[A-Za-z0-9]{20,}"),
        "Credential exposure: possible OpenAI API key",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"sk-ant-[A-Za-z0-9_-]{90,}"),
        "Credential exposure: possible Anthropic API key",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"AKIA[0-9A-Z]{16}"),
        "Credential exposure: AWS access key ID",
        ScanSeverity.CRITICAL,
    ),
]

EXFILTRATION_PATTERNS: PatternList = [
    (
        re.compile(r"(?:curl|wget|fetch|http\.?get)\s+.*(?:pastebin|ngrok|webhook\.site|requestbin)", re.IGNORECASE),
        "Data exfiltration: suspicious external endpoint",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"base64\s+(?:encode|decode).*(?:curl|wget|fetch)", re.IGNORECASE),
        "Data exfiltration: base64 encoding with network transfer",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(
            r"(?:curl|wget|fetch|requests\.(?:get|post)|httpx?\.(?:get|post))\s*[\(]?[^\n]*\$\{?\w*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL|API)",
            re.IGNORECASE,
        ),
        "Data exfiltration: HTTP request interpolating secret variable",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\$HOME/\.(?:ssh|aws|kube|docker|gnupg)\b|~/\.(?:ssh|aws|kube|docker|gnupg)\b", re.IGNORECASE),
        "Data exfiltration: access to sensitive credential directory",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bprintenv\b|env\s*\|", re.IGNORECASE),
        "Data exfiltration: dump all environment variables",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bos\.getenv\s*\(\s*[^\)]*(?:KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL)", re.IGNORECASE),
        "Data exfiltration: os.getenv reading secret variable",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"\bdict\s*\(\s*os\.environ\s*\)|os\.environ\.(?:items|values|copy)\s*\(", re.IGNORECASE),
        "Data exfiltration: bulk environment variable access",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\{[^}]*os\.environ[^}]*\}", re.IGNORECASE),
        "Data exfiltration: environment variable dict comprehension",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r">\s*/tmp/[^\s]*\s*&&\s*(?:curl|wget|nc|python)", re.IGNORECASE),
        "Data exfiltration: /tmp staging followed by exfiltration",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"!\[.*\]\(https?://[^\)]*\$\{?", re.IGNORECASE),
        "Data exfiltration: markdown image URL with variable interpolation",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(
            r"(include|output|print|send|share)\s+(?:\w+\s+)*(conversation|chat\s+history|previous\s+messages|context)",
            re.IGNORECASE,
        ),
        "Data exfiltration: context window leakage instruction",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"(send|post|upload|transmit)\s+.*\s+(to|at)\s+https?://", re.IGNORECASE),
        "Data exfiltration: instruction to send data to external URL",
        ScanSeverity.HIGH,
    ),
]

PROMPT_SECRET_EXFILTRATION_PATTERNS: PatternList = [
    (
        re.compile(
            r"(?:\bread\b|\bcat\b|\bprint\b|\bget\b|\baccess\b|\bload\b|\bextract\b)[\s\S]{0,100}"
            r"(?:\.env|id_rsa|id_ed25519|\.ssh/|\.aws/|\.kube/|credentials\.json|token\.txt|master\.key)"
            r"(?<!\.example)(?<!\.sample)(?<!\.template)[\s\S]{0,100}"
            r"(?:\bsend\b|\bpost\b|\bupload\b|\bmail\b|\btransmit\b|\bforward\b|\bcurl\b|\bwget\b|\bhttp\b)",
            re.IGNORECASE,
        ),
        "Prompt exfiltration: instruction reads secret credentials and transfers outbound",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(
            r"(?:\bsend\b|\bpost\b|\bupload\b|\bmail\b|\btransmit\b|\bforward\b|\bcurl\b|\bwget\b)[\s\S]{0,100}"
            r"(?:\.env|id_rsa|id_ed25519|\.ssh/|\.aws/|\.kube/|credentials\.json|token\.txt|master\.key)"
            r"(?<!\.example)(?<!\.sample)(?<!\.template)[\s\S]{0,100}"
            r"(?:to\s+(?:https?://|remote|webhook|endpoint|external|server|mail|email))",
            re.IGNORECASE,
        ),
        "Prompt exfiltration: instruction sends local secret credentials to external endpoint",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(
            r"(?:curl|wget|fetch|requests\.(?:get|post)|httpx?\.(?:get|post))\s+.*"
            r"(?:-d|--data|--data-raw|--data-binary|body=)[\s\S]{0,80}"
            r"(?:cat\s+|\$\(?cat\s+)?.*(?:\.env|id_rsa|\.aws/credentials|\.ssh/)",
            re.IGNORECASE,
        ),
        "Prompt exfiltration: direct shell/script exfiltration embedding secret file in payload",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(
            r"(?:base64|xxd|hexdump)[\s\S]{0,60}"
            r"(?:\.env|id_rsa|\.ssh/|\.aws/credentials)"
            r"(?<!\.example)(?<!\.sample)(?<!\.template)[\s\S]{0,80}"
            r"(?:curl|wget|nc|socat|webhook)",
            re.IGNORECASE,
        ),
        "Prompt exfiltration: encoded credential payload piped to network tool",
        ScanSeverity.CRITICAL,
    ),
]
