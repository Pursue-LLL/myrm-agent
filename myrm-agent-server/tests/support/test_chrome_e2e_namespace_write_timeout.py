"""NAMESPACE_WRITE chrome_e2e must use RESOURCE_WRITE pytest-timeout floor (810s), not READ (510s)."""

from __future__ import annotations

import pytest
from dev_gate.contract import LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC

from tests.conftest import _apply_chrome_e2e_lane_timeout


class _NamespaceWriteItem:
    def __init__(self) -> None:
        self.own_markers = [
            pytest.mark.chrome_e2e(
                execution_mode="SHARED",
                access_scope="NAMESPACE_WRITE",
                workload="STANDARD",
            ),
            pytest.mark.timeout(600),
        ]

    def iter_markers(self, name: str | None = None):
        if name is None:
            yield from self.own_markers
            return
        for marker in self.own_markers:
            if marker.name == name:
                yield marker

    def add_marker(self, marker: pytest.Mark) -> None:
        self.own_markers.append(marker)

    def get_closest_marker(self, name: str) -> pytest.Mark | None:
        for marker in reversed(self.own_markers):
            if marker.name == name:
                return marker
        return None


def test_namespace_write_standard_uses_resource_write_timeout_floor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "dev_gate.contract.parallel_live_pytest_timeout_floor_sec",
        lambda base: base,
    )
    item = _NamespaceWriteItem()
    _apply_chrome_e2e_lane_timeout(item)
    timeout_marker = item.get_closest_marker("timeout")
    assert timeout_marker is not None
    assert int(timeout_marker.args[0]) == LIVE_CHROME_E2E_PYTEST_TIMEOUT_SEC
