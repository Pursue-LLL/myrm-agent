"""The tray icon follows the menu bar's appearance instead of drawing its own pixels.

A macOS template icon is tinted by the system: white on a dark menu bar, black on a light one. The tray
library's `set_icon` swaps the image and resets the template flag, so an icon left without the flag is drawn
with its raw pixels, pure black, and disappears into a dark menu bar. Every swap therefore goes through
`apply_tray_icon`, which restores the flag inside the same main-thread task: when the two calls run apart, the
window server can render the in-between state and the icon flashes black for a frame. The tray handle has a
non-atomic reference count, so the task releases its copy before it wakes the caller and the caller waits for
that signal; a task that is not waited for lets two threads touch the count at once and corrupts the heap. The
icon is also created as a template.
"""

from __future__ import annotations

import re

import pytest

from tests.support.desktop_release import DESKTOP

_TRAY_RS = DESKTOP / "src-tauri/src/app/tray.rs"
# The functions that change the icon after it was created: the frontend's status sync and the Rust-side watchdogs.
_ICON_SWAPPERS = ("set_tray_status", "update_native_tray_status")
# The body of the closure handed to `run_on_main_thread`; rustfmt closes it with `})` at the helper's indent.
_MAIN_THREAD_TASK = re.compile(r"run_on_main_thread\(move \|\| \{(.*?)^    \}\)", re.DOTALL | re.MULTILINE)


def _function(source: str, name: str) -> str:
    """A top-level function's text; rustfmt closes it with a brace in the first column."""
    match = re.search(rf"^(?:pub )?fn {name}\b.*?^\}}", source, re.DOTALL | re.MULTILINE)
    assert match, f"tray.rs has no function {name}"
    return match.group(0)


@pytest.fixture(scope="module")
def source() -> str:
    return _TRAY_RS.read_text(encoding="utf-8")


def test_the_only_icon_swap_lives_in_the_helper(source: str) -> None:
    helper = _function(source, "apply_tray_icon")

    assert source.count(".set_icon(") == helper.count(".set_icon(") == 1


def test_the_swap_and_the_template_restore_run_in_one_main_thread_task(source: str) -> None:
    helper = _function(source, "apply_tray_icon")

    tasks = _MAIN_THREAD_TASK.findall(helper)

    assert helper.count("run_on_main_thread(") == len(tasks) == 1
    swap, restore = tasks[0].find(".set_icon("), tasks[0].find(".set_icon_as_template(true)")
    assert 0 <= swap < restore


def test_the_task_releases_its_tray_before_waking_the_waiting_caller(source: str) -> None:
    helper = _function(source, "apply_tray_icon")
    task = _MAIN_THREAD_TASK.search(helper)

    assert task, "apply_tray_icon has no main-thread task"
    release, wake = task.group(1).find("drop(tray)"), task.group(1).find(".send(")
    assert 0 <= release < wake
    assert ".recv()" in helper[task.end() :]


@pytest.mark.parametrize("name", _ICON_SWAPPERS)
def test_a_status_update_swaps_the_icon_through_the_helper(source: str, name: str) -> None:
    body = _function(source, name)

    assert "apply_tray_icon(" in body
    assert ".set_icon(" not in body


def test_the_icon_is_created_as_a_template(source: str) -> None:
    assert ".icon_as_template(true)" in _function(source, "setup_tray")
