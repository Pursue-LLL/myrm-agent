"""The identity of a memoised model call.

[INPUT]
- __future__
- hashlib::sha256
- json::dumps
- dataclasses::dataclass

[OUTPUT]
- MemoKey: the identity of one model call inside one turn
- compute_memo_key: build a MemoKey from the call's inputs
- context_fingerprint: fingerprint of the request's messages and output-affecting parameters

[POS]
Framework-level key computation for the model-call memo ledger. A key names one model call
so that a later call with the same identity can read the recorded answer instead of paying
for the model again. The key has three parts that must never be conflated:

* **Who** — the session and the turn. The turn identity must be stable across a crash and
  the resume of that same turn, and must differ between two different turns; a caller
  supplies it (see `call_scope`), because only the caller knows which turn this is.
* **Which call** — the ordinal of the call inside that turn.
* **What was asked** — the model identity and a fingerprint of the request. The model
  identity is part of the key because a failover swaps the model mid-turn: without it, the
  answer produced by the first model would be handed back as the second model's answer.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

# Parameters that change what the model answers. Anything outside this list (logging
# switches, tracing ids, callbacks) cannot change the answer and must not split the key.
OUTPUT_AFFECTING_PARAMS = (
    "temperature",
    "top_p",
    "max_tokens",
    "seed",
    "n",
    "stop",
    "tool_choice",
    "response_format",
)

_SEP = "\x1f"


@dataclass(frozen=True)
class MemoKey:
    """The identity of one model call."""

    session_id: str
    turn_id: str
    ordinal: int
    model: str
    context_fingerprint: str

    @property
    def digest(self) -> str:
        """The storage key: a stable digest of every part."""
        raw = _SEP.join(
            (
                self.session_id,
                self.turn_id,
                str(self.ordinal),
                self.model,
                self.context_fingerprint,
            )
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def context_fingerprint(
    message_dicts: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> str:
    """Fingerprint the request's messages and the parameters that shape the answer."""
    shaped = {name: (params or {}).get(name) for name in OUTPUT_AFFECTING_PARAMS if name in (params or {})}
    payload = {"messages": message_dicts, "params": shaped}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def compute_memo_key(
    *,
    session_id: str,
    turn_id: str,
    ordinal: int,
    model: str,
    message_dicts: list[dict[str, Any]],
    params: dict[str, Any] | None = None,
) -> MemoKey:
    """Build the identity of one model call."""
    return MemoKey(
        session_id=session_id,
        turn_id=turn_id,
        ordinal=ordinal,
        model=model,
        context_fingerprint=context_fingerprint(message_dicts, params),
    )
