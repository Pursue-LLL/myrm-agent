"""Tests for dref/registry.py: the registry issues the ids, never reuses one, and carries one only for an identifiable element."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.computer_use.dref.errors import DRefStaleError
from myrm_agent_harness.toolkits.computer_use.dref.registry import DRefRegistry
from myrm_agent_harness.toolkits.computer_use.dref.types import BBox, ElementRef, SnapshotMeta

_MAIL = SnapshotMeta(ref_count=0, app_name="Mail", window_title="Inbox", scope="foreground", pid=100)


def _element(name: str, *, role: str = "AXButton", backend_key: str | None = None, y: int = 0) -> ElementRef:
    return ElementRef(
        ref_id="provisional",
        role=role,
        name=name,
        bbox=BBox(0, y, 100, 30),
        backend_key=backend_key if backend_key is not None else f"key-{name}",
    )


def _capture(*elements: ElementRef) -> dict[str, ElementRef]:
    """A raw capture as a platform script returns it: the ids are positions inside the capture."""
    return {f"d{i}": element for i, element in enumerate(elements)}


def _names(refs: dict[str, ElementRef]) -> dict[str, str]:
    return {ref_id: element.name for ref_id, element in refs.items()}


class TestIssuingIds:
    def test_first_capture_gets_consecutive_ids_in_capture_order(self) -> None:
        registry = DRefRegistry()

        adopted = registry.adopt(_capture(_element("Reply"), _element("Delete")), _MAIL)

        assert _names(adopted) == {"d0": "Reply", "d1": "Delete"}
        assert all(element.ref_id == ref_id for ref_id, element in adopted.items())
        assert registry.all_refs() == adopted

    def test_ids_inside_the_capture_never_become_registry_ids(self) -> None:
        registry = DRefRegistry()

        adopted = registry.adopt({"x9": _element("Reply"), "x3": _element("Delete")}, _MAIL)

        assert _names(adopted) == {"d0": "Reply", "d1": "Delete"}

    def test_an_id_is_never_reused_for_another_element(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("A"), _element("B")), _MAIL)

        second = registry.adopt(_capture(_element("B"), _element("C")), _MAIL)
        third = registry.adopt(_capture(_element("A"), _element("B")), _MAIL)

        assert _names(second) == {"d1": "B", "d2": "C"}
        assert _names(third) == {"d3": "A", "d1": "B"}

    def test_the_counter_survives_clear(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("A")), _MAIL)
        registry.clear()

        adopted = registry.adopt(_capture(_element("A")), _MAIL)

        assert _names(adopted) == {"d1": "A"}
        with pytest.raises(DRefStaleError):
            registry.resolve("d0")

    def test_generation_counts_every_write(self) -> None:
        registry = DRefRegistry()
        assert registry.generation == 0

        registry.adopt(_capture(_element("A")), _MAIL)
        registry.adopt(_capture(_element("A")), _MAIL)
        registry.clear()

        assert registry.generation == 3

    def test_the_returned_refs_are_a_copy(self) -> None:
        registry = DRefRegistry()
        adopted = registry.adopt(_capture(_element("A")), _MAIL)

        adopted.clear()

        assert _names(registry.all_refs()) == {"d0": "A"}


class TestCarryingIds:
    def test_a_unique_element_keeps_its_id_and_takes_the_new_locator(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply", backend_key="old")), _MAIL)

        registry.adopt(_capture(_element("Reply", backend_key="new")), _MAIL)

        assert registry.resolve("d0").element.backend_key == "new"

    def test_an_element_inserted_above_does_not_shift_the_ids_of_the_others(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply"), _element("Delete"), _element("Archive")), _MAIL)

        after = registry.adopt(
            _capture(_element("Banner"), _element("Reply"), _element("Delete"), _element("Archive")), _MAIL
        )

        assert _names(after) == {"d3": "Banner", "d0": "Reply", "d1": "Delete", "d2": "Archive"}
        assert registry.resolve("d1").element.name == "Delete"

    def test_a_unique_element_keeps_its_id_wherever_it_moves(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply", y=0), _element("Delete", y=40)), _MAIL)

        after = registry.adopt(_capture(_element("Delete", y=0), _element("Reply", y=40)), _MAIL)

        assert _names(after) == {"d1": "Delete", "d0": "Reply"}

    def test_a_removed_element_is_stale_and_its_neighbour_is_not_aliased(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply"), _element("Delete"), _element("Archive")), _MAIL)

        registry.adopt(_capture(_element("Reply"), _element("Archive")), _MAIL)

        with pytest.raises(DRefStaleError):
            registry.resolve("d1")
        assert registry.resolve("d2").element.name == "Archive"

    def test_the_same_name_with_another_role_is_another_element(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Save", role="AXButton")), _MAIL)

        after = registry.adopt(_capture(_element("Save", role="AXLink")), _MAIL)

        assert set(after) == {"d1"}

    def test_a_renamed_element_is_a_new_element(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Inbox (3)")), _MAIL)

        after = registry.adopt(_capture(_element("Inbox (4)")), _MAIL)

        assert set(after) == {"d1"}

    def test_only_the_latest_capture_is_remembered(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("A")), _MAIL)
        registry.adopt(_capture(_element("B")), _MAIL)

        third = registry.adopt(_capture(_element("A")), _MAIL)

        assert set(third) == {"d2"}

    @pytest.mark.parametrize(
        "other_app",
        [
            SnapshotMeta(ref_count=0, app_name="Safari", window_title="Inbox", scope="foreground", pid=100),
            SnapshotMeta(ref_count=0, app_name="Mail", window_title="Inbox", scope="foreground", pid=101),
        ],
        ids=["other-application", "other-process"],
    )
    def test_another_application_carries_nothing(self, other_app: SnapshotMeta) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)

        after = registry.adopt(_capture(_element("Reply")), other_app)

        assert set(after) == {"d1"}
        with pytest.raises(DRefStaleError):
            registry.resolve("d0")

    def test_another_window_of_the_same_application_is_still_the_same_application(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)
        other_window = SnapshotMeta(ref_count=0, app_name="Mail", window_title="Draft", scope="target", pid=100)

        after = registry.adopt(_capture(_element("Reply")), other_window)

        assert set(after) == {"d0"}


class TestElementsWithoutAUniqueName:
    """Unnamed elements and elements sharing a name are identified by where they are."""

    @pytest.mark.parametrize("name", ["", "   "], ids=["empty", "blank"])
    def test_an_unnamed_element_that_did_not_move_keeps_its_id(self, name: str) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element(name, y=0), _element("Reply", y=40)), _MAIL)

        after = registry.adopt(_capture(_element(name, y=0), _element("Reply", y=40)), _MAIL)

        assert set(after) == {"d0", "d1"}

    def test_an_unnamed_element_that_moved_is_a_new_element(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("", y=0)), _MAIL)

        after = registry.adopt(_capture(_element("", y=40)), _MAIL)

        assert set(after) == {"d1"}
        with pytest.raises(DRefStaleError):
            registry.resolve("d0")

    def test_an_unnamed_element_that_was_resized_is_a_new_element(self) -> None:
        registry = DRefRegistry()
        registry.adopt({"d0": _element("")}, _MAIL)
        wider = ElementRef(ref_id="x", role="AXButton", name="", bbox=BBox(0, 0, 160, 30), backend_key="k")

        after = registry.adopt({"d0": wider}, _MAIL)

        assert set(after) == {"d1"}

    def test_twins_that_did_not_move_keep_their_ids(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40)), _MAIL)

        after = registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40)), _MAIL)

        assert {ref_id: element.bbox.y for ref_id, element in after.items()} == {"d0": 0, "d1": 40}

    def test_twins_that_moved_get_new_ids(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40)), _MAIL)

        after = registry.adopt(_capture(_element("OK", y=20), _element("OK", y=60)), _MAIL)

        assert set(after) == {"d2", "d3"}

    def test_one_twin_moving_does_not_retire_the_other(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40)), _MAIL)

        after = registry.adopt(_capture(_element("OK", y=0), _element("OK", y=80)), _MAIL)

        assert {ref_id: element.bbox.y for ref_id, element in after.items()} == {"d0": 0, "d2": 80}

    def test_an_element_that_gained_a_twin_keeps_its_id_while_it_stays_in_place(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("OK", y=0)), _MAIL)

        after = registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40)), _MAIL)

        assert {ref_id: element.bbox.y for ref_id, element in after.items()} == {"d0": 0, "d1": 40}

    def test_elements_that_cannot_be_told_apart_are_never_carried(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("OK"), _element("OK")), _MAIL)

        after = registry.adopt(_capture(_element("OK"), _element("OK")), _MAIL)

        assert set(after) == {"d2", "d3"}

    def test_an_unnamed_element_of_another_application_is_never_carried(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("")), _MAIL)
        other_app = SnapshotMeta(ref_count=0, app_name="Safari", window_title="Inbox", scope="foreground", pid=100)

        after = registry.adopt(_capture(_element("")), other_app)

        assert set(after) == {"d1"}

    def test_a_renamed_element_is_not_matched_by_its_place(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Inbox (3)", y=0), _element("Inbox", y=40)), _MAIL)

        after = registry.adopt(_capture(_element("Inbox (4)", y=0), _element("Inbox", y=40)), _MAIL)

        assert _names(after) == {"d2": "Inbox (4)", "d1": "Inbox"}

    def test_the_name_rule_runs_first_and_the_place_rule_serves_the_rest(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40), _element("Reply", y=80)), _MAIL)

        after = registry.adopt(_capture(_element("OK", y=0), _element("OK", y=40), _element("Reply", y=120)), _MAIL)

        assert {ref_id: (element.name, element.bbox.y) for ref_id, element in after.items()} == {
            "d0": ("OK", 0),
            "d1": ("OK", 40),
            "d2": ("Reply", 120),
        }


class TestWhatTheModelWasShown:
    def test_nothing_is_shown_until_the_session_says_so(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)

        assert registry.shown_refs() == {}
        assert registry.shown_meta is None

    def test_the_content_marked_as_shown_stays_while_later_captures_are_adopted(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply"), _element("Delete")), _MAIL)
        registry.mark_shown()

        registry.adopt(_capture(_element("Reply")), SnapshotMeta(0, "Mail", "Draft", "target", pid=100))

        assert _names(registry.shown_refs()) == {"d0": "Reply", "d1": "Delete"}
        assert registry.shown_meta == _MAIL
        assert _names(registry.all_refs()) == {"d0": "Reply"}

    def test_marking_again_moves_what_is_shown_to_the_newest_content(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)
        registry.mark_shown()
        registry.adopt(_capture(_element("Reply"), _element("Forward")), _MAIL)

        registry.mark_shown()

        assert _names(registry.shown_refs()) == {"d0": "Reply", "d1": "Forward"}

    def test_the_shown_refs_are_a_copy(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)
        registry.mark_shown()

        registry.shown_refs().clear()

        assert _names(registry.shown_refs()) == {"d0": "Reply"}

    def test_clear_forgets_what_was_shown(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)
        registry.mark_shown()

        registry.clear()

        assert registry.shown_refs() == {}
        assert registry.shown_meta is None


class TestLookup:
    @pytest.mark.parametrize("model_supplied", ["d0", "@d0", " @d0 ", "0"])
    def test_the_prefix_and_surrounding_blanks_do_not_matter(self, model_supplied: str) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)

        assert registry.resolve(model_supplied).element.name == "Reply"

    def test_resolve_names_the_snapshot_that_registered_the_element(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)

        element, meta = registry.resolve("d0")

        assert (element.name, meta) == ("Reply", _MAIL)

    @pytest.mark.parametrize(("model_supplied", "canonical"), [("d3", "d3"), ("@d3", "d3"), ("3", "d3"), (" @3", "d3")])
    def test_normalize_gives_the_canonical_id(self, model_supplied: str, canonical: str) -> None:
        assert DRefRegistry.normalize(model_supplied) == canonical

    def test_an_unknown_id_is_stale(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)

        with pytest.raises(DRefStaleError) as raised:
            registry.resolve("@d7")

        assert raised.value.ref_id == "d7"

    def test_an_empty_registry_has_nothing_to_resolve(self) -> None:
        with pytest.raises(DRefStaleError):
            DRefRegistry().resolve("d0")

    def test_clear_makes_every_id_stale_and_forgets_the_snapshot(self) -> None:
        registry = DRefRegistry()
        registry.adopt(_capture(_element("Reply")), _MAIL)

        registry.clear()

        assert registry.meta is None
        assert registry.all_refs() == {}
        with pytest.raises(DRefStaleError):
            registry.resolve("d0")
