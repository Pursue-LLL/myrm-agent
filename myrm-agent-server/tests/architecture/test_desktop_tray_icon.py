"""The tray icon follows the menu bar's appearance and its states can be told apart.

A macOS template icon is tinted by the system: white on a dark menu bar, black on a light one. The tray
library's `set_icon` swaps the image and resets the template flag, so an icon left without the flag is drawn
with its raw pixels, pure black, and disappears into a dark menu bar. Every swap therefore goes through
`apply_tray_icon`, which has the library swap the image and set the flag in one call on the main thread
(`set_icon_with_as_template`); that call does nothing at all on other platforms, which swap with `set_icon`.

A template icon is drawn from its alpha channel alone, so the status icons differ by silhouette; their colours
are kept for platforms that draw the pixels as they are. The icons are created as templates too.
"""

from __future__ import annotations

import re

import pytest
from PIL import Image, ImageChops

from tests.support.desktop_release import DESKTOP

_TRAY_RS = DESKTOP / "src-tauri/src/app/tray.rs"
_ICONS = DESKTOP / "src-tauri/icons"
# The functions that change the icon after it was created: the frontend's status sync and the Rust-side watchdogs.
_ICON_SWAPPERS = ("set_tray_status", "update_native_tray_status")
_PLATFORM_SPLIT = re.compile(r'if cfg!\(target_os = "macos"\) \{(?P<macos>[^{}]*)\} else \{(?P<other>[^{}]*)\}')
_MACOS_SWAP = re.compile(r"\.set_icon_with_as_template\(\s*Some\(icon\),\s*true\s*\)")
_PLAIN_SWAP = re.compile(r"\.set_icon\(\s*Some\(icon\)\s*\)")
_EMBEDDED_ICON = re.compile(r"icons/(tray_icon[\w@]*\.png)")
# Status icons are told apart by this many pixels whose opacity differs clearly; a lone badge merged into the glyph
# differs by about 50.
_MIN_SILHOUETTE_DIFFERENCE = 64
_BADGE_COLORS = {"busy": (34, 197, 94), "degraded": (245, 158, 11)}


def _function(source: str, name: str) -> str:
    """A top-level function's text; rustfmt closes it with a brace in the first column."""
    match = re.search(rf"^(?:pub )?fn {name}\b.*?^\}}", source, re.DOTALL | re.MULTILINE)
    assert match, f"tray.rs has no function {name}"
    return match.group(0)


def _icon(status: str) -> Image.Image:
    name = "tray_icon@2x.png" if status == "idle" else f"tray_icon_{status}@2x.png"
    return Image.open(_ICONS / name).convert("RGBA")


@pytest.fixture(scope="module")
def source() -> str:
    return _TRAY_RS.read_text(encoding="utf-8")


def test_the_only_icon_swaps_live_in_the_helper(source: str) -> None:
    helper = _function(source, "apply_tray_icon")

    for call in (".set_icon(", ".set_icon_with_as_template("):
        assert source.count(call) == helper.count(call) == 1
    assert ".set_icon_as_template(" not in source


def test_the_swap_runs_on_the_main_thread_through_tauri(source: str) -> None:
    assert "with_inner_tray_icon(" in _function(source, "apply_tray_icon")


def test_macos_swaps_the_image_and_sets_the_template_flag_in_one_call(source: str) -> None:
    split = _PLATFORM_SPLIT.search(_function(source, "apply_tray_icon"))

    assert split, "apply_tray_icon does not branch on the platform"
    assert _MACOS_SWAP.search(split.group("macos"))


def test_other_platforms_swap_with_the_plain_call(source: str) -> None:
    split = _PLATFORM_SPLIT.search(_function(source, "apply_tray_icon"))

    assert split, "apply_tray_icon does not branch on the platform"
    assert _PLAIN_SWAP.search(split.group("other"))
    assert "with_as_template" not in split.group("other")


@pytest.mark.parametrize("name", _ICON_SWAPPERS)
def test_a_status_update_swaps_the_icon_through_the_helper(source: str, name: str) -> None:
    body = _function(source, name)

    assert "apply_tray_icon(" in body
    assert ".set_icon(" not in body


def test_the_icon_is_created_as_a_template(source: str) -> None:
    assert ".icon_as_template(true)" in _function(source, "setup_tray")


def test_every_tray_icon_file_is_embedded_by_the_shell(source: str) -> None:
    on_disk = {path.name for path in _ICONS.glob("tray_icon*.png")}

    assert on_disk == set(_EMBEDDED_ICON.findall(source))


@pytest.mark.parametrize(("first", "second"), [("idle", "busy"), ("idle", "degraded"), ("busy", "degraded")])
def test_the_status_icons_differ_in_silhouette(first: str, second: str) -> None:
    opacity_change = ImageChops.difference(_icon(first).getchannel("A"), _icon(second).getchannel("A"))
    clearly_different = opacity_change.point(lambda value: 255 if value > 32 else 0).histogram()[255]

    assert clearly_different >= _MIN_SILHOUETTE_DIFFERENCE


@pytest.mark.parametrize("status", _BADGE_COLORS)
def test_a_status_icon_keeps_its_badge_colour(status: str) -> None:
    colors = _icon(status).getcolors(maxcolors=4096) or []

    assert _BADGE_COLORS[status] in {color[:3] for _, color in colors if color[3] == 255}
