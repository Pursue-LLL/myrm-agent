"""Model catalog store: the bundled snapshot, runtime registrations and the lookup rules.

[INPUT]
- data/model_catalog.json (POS: trimmed snapshot of the community model price and context-window table)

[OUTPUT]
- ModelInfo: one model's catalog entry (read-only mapping of capability flags, limits and prices)
- model_info: the entry for a model id under the provider-strict rules, or None when the catalog does not know it
- model_facts: the same lookup, widened for capability and limit questions: a gateway route resolves to the model itself
- register_model: overlay an entry at runtime (user-defined models, corrected prices)
- known_models: every entry, snapshot plus registrations
- is_deprecated: whether an entry's deprecation date has come

[POS]
Single source of model facts (context window, output ceiling, prices, capability flags) for cost accounting,
budget clamps, native-search detection and the model listings. The snapshot is loaded once, on first use.

Lookup ignores case: an exact spelling wins, otherwise the one entry whose key differs only by case (the first in key
order when two do). Beyond that ``model_info`` is provider-strict: ``provider/model`` resolves to the provider's own
entry or to a bare entry owned by that same provider, never to another provider's price for a similarly named model; a
bare id with a ``provider`` hint is resolved the same way when the id is not itself a key. ``model_facts`` adds one
step for facts that belong to the model rather than the route (window, vision, reasoning): when the strict lookup
finds nothing it drops the leading gateway segments one by one. Billing and routing decisions stay on ``model_info``.

A registration overlays the entry the snapshot resolves for that id: limits and capability flags it does not state
carry over, while stated prices (flat rates or ``tiered_pricing``) replace the catalog's whole price group, so an
official cache, long-prompt or tier rate never mixes into a user's own rates.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Callable, Mapping
from datetime import date
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


@lru_cache(maxsize=1)
def _snapshot_by_lowercase() -> Mapping[str, str]:
    """Lower-cased key -> the snapshot key spelling it stands for (first in key order wins a collision)."""
    index: dict[str, str] = {}
    for key in sorted(_snapshot()):
        index.setdefault(key.lower(), key)
    return index


def known_models() -> dict[str, ModelInfo]:
    """Snapshot entries overlaid with runtime registrations."""
    with _LOCK:
        return {**_snapshot(), **_REGISTERED}


def _snapshot_entry(key: str) -> ModelInfo | None:
    snapshot = _snapshot()
    if (exact := snapshot.get(key)) is not None:
        return exact
    spelled = _snapshot_by_lowercase().get(key.lower())
    return snapshot[spelled] if spelled is not None else None


def _entry(key: str) -> ModelInfo | None:
    with _LOCK:
        registered = _REGISTERED.get(key)
    if registered is not None:
        return registered
    if (exact := _snapshot().get(key)) is not None:
        return exact
    lowered = key.lower()
    with _LOCK:
        for name, entry in _REGISTERED.items():
            if name.lower() == lowered:
                return entry
    return _snapshot_entry(key)


def _resolve(model: str, provider: str | None, entry: Callable[[str], ModelInfo | None]) -> ModelInfo | None:
    segment, sep, bare = model.partition("/")
    owner = (segment if sep else (provider or "")).lower() or None
    bare = bare if sep else model
    if (exact := entry(model)) is not None:
        return exact
    if owner is None:
        return entry(bare)
    if (qualified := entry(f"{owner}/{bare}")) is not None:
        return qualified
    unqualified = entry(bare)
    if unqualified is not None and str(unqualified.get("provider", "")).lower() == owner:
        return unqualified
    return None


def model_info(model: str, provider: str | None = None) -> ModelInfo | None:
    """The catalog entry for ``model`` (``provider/id`` or a bare id); ``provider`` is the owner hint for a bare id."""
    return _resolve(model, provider, _entry) if model else None


def model_facts(model: str, provider: str | None = None) -> ModelInfo | None:
    """``model_info``, then the model itself behind a gateway route (``gateway/provider/model`` -> ``model``).

    For questions whose answer belongs to the model, not to the route it is reached through. Never use it to bill a
    call or to route one: a route the catalog does not list may bill differently from the model's own listing (a list
    price shown to the user is fine; the cost engine labels such a price as an estimate).
    """
    if (info := model_info(model, provider)) is not None:
        return info
    segments = model.split("/")
    for start in range(1, len(segments)):
        if (info := model_info("/".join(segments[start:]))) is not None:
            return info
    return None


def _is_price(field: str) -> bool:
    return "_cost" in field or field == "tiered_pricing"


def register_model(model: str, info: ModelInfo) -> None:
    """Overlay ``info`` on what the snapshot resolves for ``model``; a registration beats the snapshot."""
    base = dict(_resolve(model, None, _snapshot_entry) or {}) if model else {}
    if any(map(_is_price, info)):
        base = {field: value for field, value in base.items() if not _is_price(field)}
    with _LOCK:
        _REGISTERED[model] = {**base, **info}


def is_deprecated(info: ModelInfo, *, today: date | None = None) -> bool:
    """True once the entry's ``deprecation_date`` (``YYYY-MM-DD``) has come; an absent or malformed date never is."""
    stated = info.get("deprecation_date")
    if not isinstance(stated, str):
        return False
    try:
        return date.fromisoformat(stated) <= (today or date.today())
    except ValueError:
        return False
