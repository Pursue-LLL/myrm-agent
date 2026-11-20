"""Session-scoped @dref registry.

[INPUT]
- dref.errors::DRefStaleError (POS: stale ref lookup errors)
- dref.types::{ElementRef, SnapshotMeta} (POS: ref entries and snapshot metadata)

[OUTPUT]
- DRefRegistry: session-scoped @dref map. It issues the ids itself, never reuses an id for a different element, keeps
  an id across captures only for an element it can identify, and remembers which content the model was last shown

[POS]
Session-scoped registry for desktop @dref entries during a computer_use session. A capture enters only through
`adopt`; the desktop session calls it from a single place that runs the sensitive-app check first.
"""

from __future__ import annotations

from collections.abc import Callable, Hashable, Mapping
from dataclasses import dataclass, replace
from typing import NamedTuple

from myrm_agent_harness.toolkits.computer_use.dref.errors import DRefStaleError
from myrm_agent_harness.toolkits.computer_use.dref.types import ElementRef, SnapshotMeta


@dataclass(frozen=True)
class _Content:
    """One accepted capture: its elements under registry ids and the snapshot it came from."""

    refs: dict[str, ElementRef]
    meta: SnapshotMeta


class ResolvedRef(NamedTuple):
    """The element a reference names together with the snapshot that registered it."""

    element: ElementRef
    meta: SnapshotMeta


def _by_name(element: ElementRef) -> Hashable | None:
    """A named element is the same element wherever it moves; an unnamed one has no name to go by."""
    return (element.role, element.name) if element.name.strip() else None


def _by_place(element: ElementRef) -> Hashable:
    """An element that kept its role, name, position and size is the same element, named or not."""
    return (element.role, element.name, element.bbox)


def _unique_pairs(
    held: Mapping[str, ElementRef],
    capture: Mapping[str, ElementRef],
    identity: Callable[[ElementRef], Hashable | None],
) -> dict[str, str]:
    """Capture id -> held id for every identity that exactly one element has on each side."""

    def group(refs: Mapping[str, ElementRef]) -> dict[Hashable, list[str]]:
        groups: dict[Hashable, list[str]] = {}
        for ref_id, element in refs.items():
            if (key := identity(element)) is not None:
                groups.setdefault(key, []).append(ref_id)
        return groups

    held_groups = group(held)
    return {
        capture_ids[0]: held_groups[key][0]
        for key, capture_ids in group(capture).items()
        if len(capture_ids) == 1 and len(held_groups.get(key, ())) == 1
    }


class DRefRegistry:
    """Maps @dref ids to the elements of the latest capture the desktop session accepted."""

    def __init__(self) -> None:
        self._content: _Content | None = None
        self._shown: _Content | None = None
        self._generation: int = 0
        self._next_id: int = 0

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def meta(self) -> SnapshotMeta | None:
        return self._content.meta if self._content else None

    @property
    def shown_meta(self) -> SnapshotMeta | None:
        """Snapshot metadata of the content the model was last shown."""
        return self._shown.meta if self._shown else None

    def adopt(self, capture: Mapping[str, ElementRef], meta: SnapshotMeta) -> dict[str, ElementRef]:
        """Make one capture the registry content and return its elements keyed by their registry ids.

        The ids inside `capture` only tell its elements apart. An element keeps the id it already has in the
        registry only when the capture is of the same application and the element can be identified: by its role and
        name when both are unique on both sides, otherwise by role, name, position and size when it did not move.
        Every other element gets a fresh id. An id a model remembers therefore either still names the same element
        or no longer resolves.
        """
        carried = self._carried_ids(capture, meta)
        adopted: dict[str, ElementRef] = {}
        for capture_id, element in capture.items():
            ref_id = carried.get(capture_id) or self._issue_id()
            adopted[ref_id] = replace(element, ref_id=ref_id)
        self._content = _Content(adopted, meta)
        self._generation += 1
        return dict(adopted)

    def mark_shown(self) -> None:
        """Record that the model has just been given the current content, as a full tree or as the diff completing it."""
        self._shown = self._content

    def clear(self) -> None:
        """Forget every ref and snapshot so each previously issued @dref resolves as stale."""
        self._content = None
        self._shown = None
        self._generation += 1

    @staticmethod
    def normalize(ref_id: str) -> str:
        """Registry id of a model-supplied reference: '@d3', 'd3' and '3' name the same ref."""
        normalized = ref_id.strip().removeprefix("@")
        return normalized if normalized.startswith("d") else f"d{normalized}"

    def resolve(self, ref_id: str) -> ResolvedRef:
        """The element behind a model-supplied reference and the snapshot it was registered from.

        Returning both keeps the application an action is checked against the one it is delivered to.
        """
        normalized = self.normalize(ref_id)
        content = self._content
        if content is None or normalized not in content.refs:
            raise DRefStaleError(normalized)
        return ResolvedRef(content.refs[normalized], content.meta)

    def all_refs(self) -> dict[str, ElementRef]:
        return dict(self._content.refs) if self._content else {}

    def shown_refs(self) -> dict[str, ElementRef]:
        """The elements of the content the model was last shown, under the ids it was given."""
        return dict(self._shown.refs) if self._shown else {}

    def _carried_ids(self, capture: Mapping[str, ElementRef], meta: SnapshotMeta) -> dict[str, str]:
        """Capture id -> registry id for the elements of `capture` the registry can identify."""
        content = self._content
        if content is None or not content.meta.same_app(meta):
            return {}
        carried = _unique_pairs(content.refs, capture, _by_name)
        held_ids = set(carried.values())
        carried |= _unique_pairs(
            {ref_id: element for ref_id, element in content.refs.items() if ref_id not in held_ids},
            {capture_id: element for capture_id, element in capture.items() if capture_id not in carried},
            _by_place,
        )
        return carried

    def _issue_id(self) -> str:
        ref_id = f"d{self._next_id}"
        self._next_id += 1
        return ref_id
