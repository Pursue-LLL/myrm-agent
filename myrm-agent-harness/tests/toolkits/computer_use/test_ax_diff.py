"""Tests for perception/ax_diff.py — incremental AX tree diff."""

from myrm_agent_harness.toolkits.computer_use.dref.types import (
    BBox,
    ElementRef,
    SnapshotMeta,
    SnapshotScope,
)
from myrm_agent_harness.toolkits.computer_use.perception.ax_diff import (
    RefDiff,
    compute_ref_diff,
    diff_adopted,
)
from myrm_agent_harness.toolkits.computer_use.perception.renderer import (
    render_diff_tree,
    render_snapshot_tree,
)


def _make_meta(app: str = "WPS", scope: SnapshotScope = "foreground") -> SnapshotMeta:
    return SnapshotMeta(ref_count=0, app_name=app, window_title="Sheet1", scope=scope)


def _make_ref(ref_id: str, role: str, name: str, value: str = "", x: int = 0, y: int = 0) -> ElementRef:
    return ElementRef(
        ref_id=ref_id,
        role=role,
        name=name,
        bbox=BBox(x=x, y=y, width=100, height=30),
        backend_key=f"key_{ref_id}",
        actions=("click", "fill"),
        value=value,
    )


class TestComputeRefDiff:
    """Test compute_ref_diff correctness."""

    def test_first_snapshot_full_view(self) -> None:
        curr = {"d1": _make_ref("d1", "AXTextField", "Name")}
        diff = compute_ref_diff({}, curr, None, _make_meta())
        assert diff.use_full_view is True
        assert diff.full_view_reason == "first_snapshot"

    def test_app_change_full_view(self) -> None:
        prev = {"d1": _make_ref("d1", "AXTextField", "Name")}
        curr = {"d1": _make_ref("d1", "AXTextField", "Name")}
        diff = compute_ref_diff(prev, curr, _make_meta("TextEdit"), _make_meta("WPS"))
        assert diff.use_full_view is True
        assert diff.full_view_reason == "app_changed"

    def test_no_change_zero_diff(self) -> None:
        meta = _make_meta()
        refs = {
            "d1": _make_ref("d1", "AXTextField", "Name", value="Alice", x=10, y=20),
            "d2": _make_ref("d2", "AXButton", "Submit", x=10, y=60),
        }
        diff = compute_ref_diff(refs, refs, meta, meta)
        assert diff.use_full_view is False
        assert len(diff.added) == 0
        assert len(diff.updated) == 0
        assert len(diff.removed) == 0

    def test_single_value_change(self) -> None:
        meta = _make_meta()
        prev = {
            "d1": _make_ref("d1", "AXTextField", "Name", value="", x=10, y=20),
            "d2": _make_ref("d2", "AXButton", "Submit", x=10, y=60),
        }
        curr = {
            "d1": _make_ref("d1", "AXTextField", "Name", value="Alice", x=10, y=20),
            "d2": _make_ref("d2", "AXButton", "Submit", x=10, y=60),
        }
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is False
        assert len(diff.added) == 0
        assert len(diff.updated) == 1
        assert diff.updated[0].ref_id == "d1"
        assert diff.updated[0].changed_fields == ("value",)
        assert len(diff.removed) == 0

    def test_added_and_removed(self) -> None:
        meta = _make_meta()
        stable = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"Stable{i}", x=i * 20) for i in range(5)}
        prev = {**stable, "d10": _make_ref("d10", "AXButton", "Cancel", x=200, y=60)}
        curr = {**stable, "d11": _make_ref("d11", "AXButton", "Confirm", x=200, y=100)}
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is False
        assert len(diff.added) == 1
        assert diff.added[0].ref_id == "d11"
        assert len(diff.removed) == 1
        assert "d10" in diff.removed

    def test_high_change_ratio_full_view(self) -> None:
        meta = _make_meta()
        prev = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"Btn{i}", x=i * 10) for i in range(10)}
        curr = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"New{i}", x=i * 10 + 200) for i in range(10)}
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is True
        assert "low_identity_confidence" in diff.full_view_reason or "high_change_ratio" in diff.full_view_reason

    def test_bbox_change_ignored(self) -> None:
        meta = _make_meta()
        prev = {"d1": _make_ref("d1", "AXTextField", "Name", x=10, y=20)}
        curr = {"d1": _make_ref("d1", "AXTextField", "Name", x=50, y=60)}
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is False
        assert len(diff.updated) == 0

    def test_duplicate_identity_keeps_used_candidate(self) -> None:
        """Two prev refs sharing (role, name) must not both map to one curr ref.

        The second candidate is skipped via the `used_curr` guard, so the mapping
        stays one-to-one and no phantom updated entries appear.
        """
        meta = _make_meta()
        prev = {
            "d1": _make_ref("d1", "AXButton", "OK", x=10, y=20),
            "d2": _make_ref("d2", "AXButton", "OK", x=30, y=40),
        }
        curr = {"d1": _make_ref("d1", "AXButton", "OK", x=10, y=20)}
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is False
        assert len(diff.added) == 0
        assert len(diff.updated) == 0
        assert "d2" in diff.removed

    def test_high_change_ratio_after_match(self) -> None:
        """Enough matched refs to pass identity confidence, but change ratio > 0.6."""
        meta = _make_meta()
        stable = [_make_ref(f"d{i}", "AXButton", f"Btn{i}", x=i * 10) for i in range(5)]
        prev = {r.ref_id: r for r in stable}
        prev["d10"] = _make_ref("d10", "AXButton", "Cancel", x=200, y=60)
        prev["d11"] = _make_ref("d11", "AXButton", "Retry", x=200, y=90)
        prev["d12"] = _make_ref("d12", "AXButton", "Skip", x=200, y=120)
        curr = {r.ref_id: r for r in stable}
        curr["d20"] = _make_ref("d20", "AXButton", "New1", x=300, y=60)
        curr["d21"] = _make_ref("d21", "AXButton", "New2", x=300, y=90)
        curr["d22"] = _make_ref("d22", "AXButton", "New3", x=300, y=120)
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is True
        assert "high_change_ratio" in diff.full_view_reason

    def test_low_identity_confidence_full_view(self) -> None:
        meta = _make_meta()
        prev = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"A{i}", x=i * 10) for i in range(10)}
        curr = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"Z{i}", x=i * 10) for i in range(10)}
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is True
        assert "low_identity_confidence" in diff.full_view_reason

    def test_multiple_updated_fields(self) -> None:
        meta = _make_meta()
        stable = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"Btn{i}", x=i * 20) for i in range(5)}
        prev_el = ElementRef(
            ref_id="d10",
            role="AXTextField",
            name="Name",
            bbox=BBox(x=10, y=200, width=100, height=30),
            backend_key="key_d10",
            actions=("click", "fill"),
            value="A",
        )
        curr_el = ElementRef(
            ref_id="d10",
            role="AXTextField",
            name="Name",
            bbox=BBox(x=10, y=200, width=100, height=30),
            backend_key="key_d10",
            actions=("click", "fill", "clear"),
            value="Bob",
        )
        prev = {**stable, "d10": prev_el}
        curr = {**stable, "d10": curr_el}
        diff = compute_ref_diff(prev, curr, meta, meta)
        assert diff.use_full_view is False
        assert len(diff.updated) == 1
        changed = set(diff.updated[0].changed_fields)
        assert "value" in changed
        assert "actions" in changed


class TestRenderDiffTree:
    """Test render_diff_tree output format."""

    def test_zero_change_message(self) -> None:
        meta = _make_meta()
        diff = RefDiff()
        text, enriched = render_diff_tree(meta, diff)
        assert "unchanged" in text
        assert "0 changes" in text
        assert enriched.token_estimate > 0

    def test_single_update_output(self) -> None:
        meta = _make_meta()
        from myrm_agent_harness.toolkits.computer_use.perception.ax_diff import (
            UpdatedRef,
        )

        diff = RefDiff(
            updated=[
                UpdatedRef(
                    ref_id="d1",
                    element=_make_ref("d1", "AXTextField", "Name", value="Alice"),
                    changed_fields=("value",),
                )
            ]
        )
        text, enriched = render_diff_tree(meta, diff)
        assert "1 change" in text
        assert "~ @d1" in text
        assert "value" in text
        assert enriched.token_estimate > 0

    def test_diff_much_smaller_than_full(self) -> None:
        meta = SnapshotMeta(ref_count=80, app_name="WPS", window_title="Sheet1", scope="target")
        refs = {f"d{i}": _make_ref(f"d{i}", "AXButton", f"Button{i}", x=i * 10) for i in range(80)}

        full_text, _ = render_snapshot_tree(meta, refs)

        from myrm_agent_harness.toolkits.computer_use.perception.ax_diff import (
            UpdatedRef,
        )

        diff = RefDiff(
            updated=[
                UpdatedRef(
                    ref_id="d0",
                    element=_make_ref("d0", "AXButton", "Button0", value="clicked"),
                    changed_fields=("value",),
                )
            ]
        )
        diff_text, _ = render_diff_tree(meta, diff)

        assert len(diff_text) < len(full_text) * 0.2

    def test_added_removed_format(self) -> None:
        meta = _make_meta()
        diff = RefDiff(
            added=[_make_ref("d5", "AXButton", "New")],
            removed=["d3"],
        )
        text, _ = render_diff_tree(meta, diff)
        assert "+ @d5" in text
        assert "- @d3 (removed, no longer valid)" in text

    def test_diff_text_says_which_ids_stay_valid(self) -> None:
        diff = RefDiff(added=[_make_ref("d5", "AXButton", "New")], removed=["d3"])

        text, _ = render_diff_tree(_make_meta(), diff)

        assert "+ new, ~ changed, - removed" in text
        assert "@ids not listed below are unchanged and still valid" in text

    def test_zero_change_message_says_every_id_is_still_valid(self) -> None:
        text, _ = render_diff_tree(_make_meta(), RefDiff())

        assert "All @ids from the previous snapshot are still valid." in text


class TestDiffAdopted:
    """diff_adopted compares registry contents, where an id present on both sides is the same element."""

    @staticmethod
    def _registry_content(*specs: tuple[str, str, str]) -> dict[str, ElementRef]:
        """(ref_id, name, value) triples as registry content; every bbox is the same on purpose."""
        return {ref_id: _make_ref(ref_id, "AXButton", name, value=value) for ref_id, name, value in specs}

    def test_first_snapshot_full_view(self) -> None:
        curr = self._registry_content(("d0", "OK", ""))

        diff = diff_adopted({}, curr, None, _make_meta())

        assert diff.use_full_view is True
        assert diff.full_view_reason == "first_snapshot"

    def test_other_application_full_view(self) -> None:
        refs = self._registry_content(("d0", "OK", ""))

        diff = diff_adopted(refs, refs, _make_meta("TextEdit"), _make_meta("WPS"))

        assert diff.use_full_view is True
        assert diff.full_view_reason == "app_changed"

    def test_other_process_of_the_same_application_full_view(self) -> None:
        refs = self._registry_content(("d0", "OK", ""))
        prev_meta = SnapshotMeta(ref_count=1, app_name="WPS", window_title="a", scope="foreground", pid=10)
        curr_meta = SnapshotMeta(ref_count=1, app_name="WPS", window_title="a", scope="foreground", pid=11)

        diff = diff_adopted(refs, refs, prev_meta, curr_meta)

        assert diff.full_view_reason == "app_changed"

    def test_same_ids_and_content_is_an_empty_diff(self) -> None:
        refs = self._registry_content(("d0", "OK", ""), ("d1", "Cancel", ""))

        diff = diff_adopted(refs, dict(refs), _make_meta(), _make_meta())

        assert diff.use_full_view is False
        assert (diff.added, diff.updated, diff.removed) == ([], [], [])

    def test_new_ids_are_added_and_missing_ids_are_removed_by_id_alone(self) -> None:
        stable = [(f"d{i}", f"Stable{i}", "") for i in range(5)]
        prev = self._registry_content(*stable, ("d5", "Cancel", ""))
        curr = self._registry_content(*stable, ("d6", "Confirm", ""))

        diff = diff_adopted(prev, curr, _make_meta(), _make_meta())

        assert [el.ref_id for el in diff.added] == ["d6"]
        assert diff.removed == ["d5"]
        assert diff.updated == []

    def test_same_id_with_a_new_value_is_updated(self) -> None:
        stable = [(f"d{i}", f"Stable{i}", "") for i in range(5)]
        prev = self._registry_content(*stable, ("d5", "Name", ""))
        curr = self._registry_content(*stable, ("d5", "Name", "Alice"))

        diff = diff_adopted(prev, curr, _make_meta(), _make_meta())

        assert [(u.ref_id, u.changed_fields) for u in diff.updated] == [("d5", ("value",))]
        assert diff.added == []
        assert diff.removed == []

    def test_mostly_new_ids_full_view_but_the_lists_stay_authoritative(self) -> None:
        prev = self._registry_content(*[(f"d{i}", f"Old{i}", "") for i in range(4)])
        curr = self._registry_content(*[(f"d{i + 4}", f"New{i}", "") for i in range(4)])

        diff = diff_adopted(prev, curr, _make_meta(), _make_meta())

        assert diff.use_full_view is True
        assert diff.full_view_reason == "high_change_ratio(8/4)"
        assert len(diff.added) == 4
        assert len(diff.removed) == 4
