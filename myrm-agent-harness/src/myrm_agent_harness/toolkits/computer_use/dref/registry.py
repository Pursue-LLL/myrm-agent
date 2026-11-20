"""Session-scoped @dref registry.

[INPUT]
- dref.errors::DRefStaleError (POS: stale ref lookup errors)
- dref.types::{ElementRef, SnapshotMeta} (POS: ref entries and snapshot metadata)

[OUTPUT]
- DRefRegistry: session-scoped @dref map. It issues the ids itself, never reuses an id for a different element, and
  keeps an id across captures only for an element it can identify

[POS]
Session-scoped registry for desktop @dref entries during a computer_use session. A capture enters only through
`adopt`; the desktop session calls it from a single place that runs the sensitive-app check first.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace

from myrm_agent_harness.toolkits.computer_use.dref.errors import DRefStaleError
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta


def _ids_by_identity(refs: Mapping[str, ElementRef]) -> dict[tuple[str, str], list[str]]:
    """Group the ids of the named elements by (role, name); an unnamed element has no identity to match on."""
    groups: dict[tuple[str, str], list[str]] = {}
    for ref_id, element in refs.items():
        if element.name.strip():
            groups.setdefault((element.role, element.name), []).append(ref_id)
    return groups


class DRefRegistry:
    """Maps @dref ids to the elements of the latest capture the desktop session accepted."""

    def __init__(self) -> None:
        self._refs: dict[str, ElementRef] = {}
        self._meta: SnapshotMeta | None = None
        self._generation: int = 0
        self._next_id: int = 0

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def meta(self) -> SnapshotMeta | None:
        return self._meta

    def adopt(self, capture: Mapping[str, ElementRef], meta: SnapshotMeta) -> dict[str, ElementRef]:
        """Make one capture the registry content and return its elements keyed by their registry ids.

        The ids inside `capture` only tell its elements apart. An element keeps the id it already has in the
        registry only when the capture is of the same application and the element's (role, name) is unique among
        the named elements on both sides; every other element gets a fresh id. An id a model remembers therefore
        either still names the same element or no longer resolves.
        """
        carried = self._carried_ids(capture, meta)
        adopted: dict[str, ElementRef] = {}
        for capture_id, element in capture.items():
            ref_id = carried.get(capture_id) or self._issue_id()
            adopted[ref_id] = replace(element, ref_id=ref_id)
        self._refs = adopted
        self._meta = meta
        self._generation += 1
        return dict(adopted)

    def clear(self) -> None:
        """Forget every ref and snapshot so each previously issued @dref resolves as stale."""
        self._refs = {}
        self._meta = None
        self._generation += 1

    @staticmethod
    def normalize(ref_id: str) -> str:
        """Registry id of a model-supplied reference: '@d3', 'd3' and '3' name the same ref."""
        normalized = ref_id.strip().removeprefix("@")
        return normalized if normalized.startswith("d") else f"d{normalized}"

    def get(self, ref_id: str) -> ElementRef:
        normalized = self.normalize(ref_id)
        element = self._refs.get(normalized)
        if element is None:
            raise DRefStaleError(normalized)
        return element

    def all_refs(self) -> dict[str, ElementRef]:
        return dict(self._refs)

    def _carried_ids(self, capture: Mapping[str, ElementRef], meta: SnapshotMeta) -> dict[str, str]:
        """Capture id -> registry id for the elements of `capture` the registry can identify."""
        if self._meta is None or not self._meta.same_app(meta):
            return {}
        held = _ids_by_identity(self._refs)
        return {
            capture_ids[0]: held[identity][0]
            for identity, capture_ids in _ids_by_identity(capture).items()
            if len(capture_ids) == 1 and len(held.get(identity, ())) == 1
        }

    def _issue_id(self) -> str:
        ref_id = f"d{self._next_id}"
        self._next_id += 1
        return ref_id
