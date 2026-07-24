"""R43: chrome_e2e pytest-timeout must cap per-item marks to lane SSOT (600s)."""

from __future__ import annotations

import pytest

from tests.conftest import _apply_chrome_e2e_lane_timeout


class _TimeoutCapItem:
    def __init__(self) -> None:
        self.own_markers = [
            pytest.mark.chrome_e2e(
                lane="LIVE_AGENT", shared_hot=True, private_backend=False
            ),
            pytest.mark.timeout(1800),
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


def test_r43_caps_high_desktop_timeout_mark_to_600() -> None:
    item = _TimeoutCapItem()
    _apply_chrome_e2e_lane_timeout(item)
    timeout_marker = item.get_closest_marker("timeout")
    assert timeout_marker is not None
    assert int(timeout_marker.args[0]) == 600
