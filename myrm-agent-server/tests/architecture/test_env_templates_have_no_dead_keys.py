"""Architecture test: every key in a committed env template must have a real reader.

A template listing a key nothing reads is worse than no template: a maintainer copies it,
sets the value, and sees no effect. That is how `BASELINE_SYNC_INTERVAL` and the
`RERANKER_*` triple survived — nothing failed when their readers disappeared.

The scan is generous about *where* a reader may live (server app, harness, scripts, tests,
Dockerfile, compose) and strict about *whether* one exists: a key passes when its name
appears anywhere outside env files and markdown. Keys joined at runtime from a
`SettingsConfigDict(env_prefix=...)` are covered by prefix without a per-key whitelist.
"""

from __future__ import annotations

import re
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_REPO_ROOT = _SERVER_ROOT.parent

# Committed templates that claim to describe the keys a deployment or a test run needs.
_TEMPLATES = (
    _SERVER_ROOT / ".env.example",
    _SERVER_ROOT / ".env.test.example",
    _SERVER_ROOT / ".env.sandbox.example",
)

# Where a reader may live. Anything outside these trees cannot be a reader.
_READER_ROOTS = (
    _SERVER_ROOT / "app",
    _SERVER_ROOT / "tests",
    _SERVER_ROOT / "scripts",
    _REPO_ROOT / "myrm-agent-harness" / "src",
    _REPO_ROOT / "scripts",
)
_READER_FILES = (
    _SERVER_ROOT / "Dockerfile",
    _SERVER_ROOT / "docker-compose.yaml",
)

_SKIP_DIRNAMES = frozenset(
    {"node_modules", ".venv", "__pycache__", ".git", ".next", "dist", "build", "target"}
)

_KEY_LINE = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]{2,})\s*=")

# Templated keys whose reader is a SettingsConfigDict(env_prefix=...) or a compose variable
# reference instead of a literal name. Any key starting with one of these is considered named.
_RUNTIME_JOINED_PREFIXES = (
    "AGENT_",
    "BASH_AUDIT_",
    "CHANNEL_DINGTALK_",
    "CODE_EXECUTION_",
    "CONTEXT_COMPACTION_TELEMETRY_",
    "ENABLE_",
    "EXECUTION_CACHE_",
    "GLOBAL_BROWSER_POOL_",
    "MCP_",
    "MEMORY_BRIEF_STATUS_TELEMETRY_",
    "MEMORY_GUARDIAN_GUARD_TELEMETRY_",
    "RATE_LIMIT_",
    "SECURITY_",
    "WEBUI_",
    "MYRM_",
)

_SCANNED_SUFFIXES = frozenset({".py", ".ts", ".tsx", ".js", ".mjs", ".sh", ".json", ".yaml", ".yml"})


def _template_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = _KEY_LINE.match(line)
        if match:
            keys.append(match.group(1))
    return keys


def _reader_corpus() -> str:
    """Concatenate every file a reader could live in."""
    chunks: list[str] = []
    for root in _READER_ROOTS:
        if not root.is_dir():
            continue
        for path in root.rglob("*"):
            if path.suffix not in _SCANNED_SUFFIXES or not path.is_file():
                continue
            if _SKIP_DIRNAMES & set(path.parts):
                continue
            try:
                chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
            except OSError:
                continue
    for path in _READER_FILES:
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8", errors="ignore"))
    return "\n".join(chunks)


def _has_reader(key: str, corpus: str) -> bool:
    if key in corpus:
        return True
    return any(key.startswith(prefix) for prefix in _RUNTIME_JOINED_PREFIXES)


def test_templates_resolve() -> None:
    """A wrong path would make the scan below pass vacuously; prove the files exist first."""
    missing = [str(t) for t in _TEMPLATES if not t.is_file()]
    assert missing == [], f"env templates not found at the expected paths: {missing}"
    missing_readers = [str(r) for r in _READER_ROOTS if not r.is_dir()]
    assert missing_readers == [], f"reader roots not found at the expected paths: {missing_readers}"


def test_every_template_key_has_a_reader() -> None:
    corpus = _reader_corpus()
    orphans: list[str] = []
    for template in _TEMPLATES:
        for key in _template_keys(template):
            if not _has_reader(key, corpus):
                orphans.append(f"{template.name}: {key}")

    assert orphans == [], (
        "these env template keys have no reader anywhere in the codebase — "
        "delete them, or wire up the code that reads them:\n" + "\n".join(sorted(set(orphans)))
    )


def test_scan_finds_readers_and_rejects_invented_keys() -> None:
    """Guard against a silently empty corpus making the assertion above vacuous."""
    corpus = _reader_corpus()
    assert len(corpus) > 100_000, f"reader corpus looks truncated ({len(corpus)} chars)"
    assert _has_reader("BASIC_API_KEY", corpus), "BASIC_API_KEY has readers; the scan must see them"
    # A name that exists nowhere, including in this file itself (which the corpus also scans).
    invented = "QWXZ" + "NONEXISTENT_PROBE"
    assert invented not in corpus
    assert not _has_reader(invented, corpus)
