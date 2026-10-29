"""The conftest guard must be active: it is the only thing between a forgotten patch and real keystrokes."""

from __future__ import annotations

import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "darwin", reason="Quartz event posting is macOS-only")


def test_quartz_event_posting_is_replaced_by_the_refusing_guard() -> None:
    quartz = pytest.importorskip("Quartz")

    # 只检查替换是否生效，不调用：守卫失效时调用会向本机真实投递事件。
    assert quartz.CGEventPost.__name__ == "refuse"
    assert quartz.CGEventPostToPid.__name__ == "refuse"
