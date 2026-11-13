"""The tray icon follows the menu bar's appearance instead of drawing its own pixels.

A macOS template icon is tinted by the system: white on a dark menu bar, black on a light one. The tray
library's `set_icon` swaps the image and resets the template flag, so an icon swapped without restoring the flag
is drawn with its raw pixels, pure black, and disappears into a dark menu bar. Every swap therefore goes
through `apply_tray_icon`, which restores the flag right after, and the icon is created as a template.
"""

from __future__ import annotations

import re

import pytest

from tests.support.desktop_release import DESKTOP

_TRAY_RS = DESKTOP / "src-tauri/src/app/tray.rs"
# The functions that change the icon after it was created: the frontend's status sync and the Rust-side watchdogs.
_ICON_SWAPPERS = ("set_tray_status", "update_native_tray_status")


def _function(source: str, name: str) -> str:
    """A top-level function's text; rustfmt closes it with a brace in the first column."""
    match = re.search(rf"^(?:pub )?fn {name}\b.*?^\}}", source, re.DOTALL | re.MULTILINE)
    assert match, f"tray.rs has no function {name}"
    return match.group(0)


@pytest.fixture(scope="module")
def source() -> str:
    return _TRAY_RS.read_text(encoding="utf-8")


def test_the_only_icon_swap_restores_the_template_flag_right_after(source: str) -> None:
    helper = _function(source, "apply_tray_icon")

    swap, restore = helper.find(".set_icon("), helper.find(".set_icon_as_template(true)")

    assert source.count(".set_icon(") == helper.count(".set_icon(") == 1
    assert 0 <= swap < restore


@pytest.mark.parametrize("name", _ICON_SWAPPERS)
def test_a_status_update_swaps_the_icon_through_the_helper(source: str, name: str) -> None:
    body = _function(source, name)

    assert "apply_tray_icon(" in body
    assert ".set_icon(" not in body


def test_the_icon_is_created_as_a_template(source: str) -> None:
    assert ".icon_as_template(true)" in _function(source, "setup_tray")
