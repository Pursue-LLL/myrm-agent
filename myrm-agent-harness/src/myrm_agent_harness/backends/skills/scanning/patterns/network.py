"""技能安全扫描模式：network 类。

[POS]
patterns 子包的一部分；纯数据，由 __init__.py 汇总。
"""

from __future__ import annotations

import re

from ..scanner import ScanSeverity
from .types import PatternList

NETWORK_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:socket\.connect|urllib\.request|requests\.(?:get|post|put|delete))\b", re.IGNORECASE),
        "Network: direct network API usage",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"\b(?:bind|listen)\s*\(\s*(?:['\"]0\.0\.0\.0|['\"]::)", re.IGNORECASE),
        "Network: opening a server socket",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bngrok\b|\blocaltunnel\b|\bserveo\b|\bcloudflared\b", re.IGNORECASE),
        "Network: tunneling service for external access",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}:\d{2,5}"),
        "Network: hardcoded IP address with port",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"webhook\.site|requestbin\.com|pipedream\.net|hookbin\.com", re.IGNORECASE),
        "Network: known data exfiltration/webhook testing service",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"pastebin\.com|hastebin\.com|ghostbin\.", re.IGNORECASE),
        "Network: paste service (possible data staging)",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"0\.0\.0\.0:\d+|INADDR_ANY", re.IGNORECASE),
        "Network: binding to all interfaces",
        ScanSeverity.HIGH,
    ),
]

DNS_TUNNELING_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:dns\.resolver|dnspython)\b", re.IGNORECASE),
        "DNS tunneling: DNS resolver library usage",
        ScanSeverity.MEDIUM,
    ),
    (
        re.compile(r"\b(?:nslookup|dig)\s+.*TXT\b", re.IGNORECASE),
        "DNS tunneling: TXT record query (potential data channel)",
        ScanSeverity.MEDIUM,
    ),
]

REVERSE_SHELL_PATTERNS: PatternList = [
    (
        re.compile(r"\bnc\s+-[lp]|ncat\s+-[lp]|\bsocat\b", re.IGNORECASE),
        "Reverse shell: netcat/socat listener",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"/bin/(?:ba)?sh\s+-i\s+.*>/dev/tcp/", re.IGNORECASE),
        "Reverse shell: bash interactive shell via /dev/tcp",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"python[23]?\s+-c\s+[\"']import\s+socket", re.IGNORECASE),
        "Reverse shell: Python one-liner socket connection",
        ScanSeverity.CRITICAL,
    ),
    (
        re.compile(r"socket\.connect\s*\(\s*\(", re.IGNORECASE),
        "Reverse shell: Python socket connect to arbitrary host",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bchild_process\.(?:exec|spawn|fork)\s*\(", re.IGNORECASE),
        "Reverse shell: Node.js child_process execution",
        ScanSeverity.HIGH,
    ),
]

CRYPTO_MINING_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:xmrig|stratum\+tcp|monero|coinhive|cryptonight)\b", re.IGNORECASE),
        "Crypto mining: cryptocurrency mining reference",
        ScanSeverity.CRITICAL,
    ),
]

CONTAINER_ESCAPE_PATTERNS: PatternList = [
    (
        re.compile(r"\b(?:docker\s+run|nsenter|unshare)\b", re.IGNORECASE),
        "Container escape: container/namespace manipulation",
        ScanSeverity.HIGH,
    ),
    (
        re.compile(r"\bmount\s+.*(?:/proc|/sys|/dev)", re.IGNORECASE),
        "Container escape: sensitive filesystem mount",
        ScanSeverity.CRITICAL,
    ),
]
