"""Model catalog store: the bundled snapshot, runtime registrations and the lookup rules.

[INPUT]
- data/model_catalog.json (POS: trimmed snapshot of the community model price and context-window table)

[OUTPUT]
- ModelInfo: one model's catalog entry (read-only mapping of capability flags, limits and prices)
- model_info: the entry for a model id, or None when the catalog does not know it
- register_model: add or replace an entry at runtime (user-defined models, corrected prices)
- known_models: every entry, snapshot plus registrations

[POS]
Single source of model facts (context window, output ceiling, prices, capability flags) for cost accounting,
budget clamps, native-search detection and the model listings. The snapshot is loaded once, on first use. An exact
key always wins. Otherwise lookup is provider-strict: ``provider/model`` resolves to the provider's own entry or to a
bare entry owned by that same provider, never to another provider's price for a similarly named model; a bare id with
a ``provider`` hint is resolved the same way when the id is not itself a key.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from typing import Final

ModelInfo = Mapping[str, object]

_SNAPSHOT: Final = Path(__file__).parent / "data" / "model_catalog.json"
_REGISTERED: dict[str, ModelInfo] = {}
_LOCK: Final = threading.Lock()


@lru_cache(maxsize=1)
def _snapshot() -> Mapping[str, ModelInfo]:
    with _SNAPSHOT.open(encoding="utf-8") as handle:
        data: dict[str, ModelInfo] = json.load(handle)
    return data


def known_models() -> dict[str, ModelInfo]:
    """Snapshot entries overlaid with runtime registrations."""
    with _LOCK:
        return {**_snapshot(), **_REGISTERED}


def register_model(model: str, info: ModelInfo) -> None:
    """Add or replace the entry for ``model``; a registration beats the snapshot."""
    with _LOCK:
        _REGISTERED[model] = dict(info)


def _entry(key: str) -> ModelInfo | None:
    with _LOCK:
        registered = _REGISTERED.get(key)
    return registered if registered is not None else _snapshot().get(key)


def model_info(model: str, provider: str | None = None) -> ModelInfo | None:
    """The catalog entry for ``model`` (``provider/id`` or a bare id); ``provider`` is the owner hint for a bare id."""
    if not model:
        return None
    segment, sep, bare = model.partition("/")
    owner = (segment if sep else (provider or "")).lower() or None
    bare = bare if sep else model
    if (exact := _entry(model)) is not None:
        return exact
    if owner is None:
        return _entry(bare)
    if (qualified := _entry(f"{owner}/{bare}")) is not None:
        return qualified
    unqualified = _entry(bare)
    if unqualified is not None and str(unqualified.get("provider", "")).lower() == owner:
        return unqualified
    return None
