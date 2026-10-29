"""Prompt-injection verdict for workspace rule file text.

[INPUT]
- agent.security.detection.prompt_guard::scan_input (POS: Input-side injection detector)
- agent.security.detection.content_boundary::detect_suspicious (POS: Boundary sanitization and security marker detection)
- utils.lru_cache::LRUCache (POS: LRU cache utility. OrderedDict-based LRU cache implementation with TTL support.)

[OUTPUT]
- check_content_safety(): (safe, blocked patterns) verdict for one rule file's text, remembered per content digest

[POS]
Safety verdict for workspace rule file text. The middleware reads every rule file on every model call, and the
injection scan dominates that read, so a verdict is remembered per content digest: a file that has not changed is
never scanned twice and an edited one is scanned on the next call.
"""

from __future__ import annotations

import hashlib
import logging
import threading

from myrm_agent_harness.utils.lru_cache import LRUCache

logger = logging.getLogger(__name__)

_BLOCK_SCORE = 0.8
_Verdict = tuple[bool, tuple[str, ...]]

# Well above the number of rule files one scan reads: an LRU walked in order by a scan longer than its capacity evicts
# every entry just before it is needed again and never hits (the verdicts stay correct, only the saving is lost).
_VERDICTS: LRUCache[_Verdict] = LRUCache(maxsize=2048, ttl=86400, id="workspace-rule-verdicts")
# ``LRUCache`` is only safe for callers on one thread and this is a library entry point. The scan itself runs outside
# the lock: two threads that miss on the same text both scan it and store the same verdict.
_VERDICTS_LOCK = threading.Lock()


def _scan(content: str, filepath: str) -> _Verdict:
    from myrm_agent_harness.agent.security.detection.content_boundary import detect_suspicious
    from myrm_agent_harness.agent.security.detection.prompt_guard import scan_input

    guard_result = scan_input(content)
    if guard_result.block_score >= _BLOCK_SCORE:
        logger.warning(
            "Workspace rule file blocked (injection detected): %s patterns=%s score=%.2f",
            filepath,
            ",".join(guard_result.patterns),
            guard_result.block_score,
        )
        return False, tuple(guard_result.patterns)

    suspicious = detect_suspicious(content)
    if suspicious:
        logger.warning(
            "Workspace rule file suspicious patterns: %s patterns=%s",
            filepath,
            ",".join(suspicious),
        )

    return True, ()


def _digest(content: str) -> str:
    # ``surrogatepass`` keeps the encoding one-to-one, so two different texts never share a key.
    return hashlib.blake2b(content.encode("utf-8", "surrogatepass"), digest_size=16).hexdigest()


def check_content_safety(content: str, filepath: str) -> tuple[bool, list[str]]:
    """Run security scans on rule file content.

    Returns (safe, blocked_patterns) where blocked_patterns is non-empty only when the content is blocked
    (safe=False). The verdict depends on the text alone: ``filepath`` only labels the warning, which is written
    when the text is scanned and not again while its verdict is remembered. The returned list is the caller's own.
    """
    key = _digest(content)
    with _VERDICTS_LOCK:
        verdict = _VERDICTS.get(key)
    if verdict is None:
        verdict = _scan(content, filepath)
        with _VERDICTS_LOCK:
            _VERDICTS.set(key, verdict)
    return verdict[0], list(verdict[1])
