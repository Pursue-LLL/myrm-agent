"""Numeric limits and intervals shared by AgentRouter routing modules.

[POS]
Constants read by router.py, router_stream, and janitor/dedup logic. Includes silence reassurance
thresholds. Unit tests can import directly.
"""

_MAX_CONCURRENT_AGENTS = 5
_MIN_PROGRESS_INTERVAL = 2.0
_MIN_STREAM_INTERVAL = 0.5
_DEDUP_TTL = 300.0
_DEDUP_MAX_SIZE = 10_000
_CLEANUP_TTL = 3600.0
_SILENCE_REASSURANCE_THRESHOLD = 300.0
_MAX_REASSURANCE_COUNT = 3
_STUCK_TASK_TIMEOUT = 600.0
