"""JSONL lines shaped like the event log writes them, for tests that feed a log to a reader."""

from __future__ import annotations

import json


def jsonl_pad(size: int) -> str:
    """One valid JSONL line of exactly ``size`` bytes."""
    return '{"pad":"' + "x" * (size - 11) + '"}\n'


def event_line(seq: int, event_type: str, payload_size: int = 0) -> str:
    """One event line with a payload of ``payload_size`` characters."""
    event = {"seq": seq, "ts": 1790000000.0 + seq, "type": event_type, "sid": "s1", "data": {"output": "p" * payload_size}}
    return json.dumps(event, ensure_ascii=False) + "\n"
