"""Which directories above a protected path the sandboxed process is able to rename.

[INPUT]
- code_execution.sandbox.sandbox_types (POS: Foundation layer for the sandbox modules)

[OUTPUT]
- Ancestor lists for paths inside, equal to, outside and between writable areas.

[POS]
Guards the rule both providers use to decide what to pin next to a read-only subpath.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.code_execution.sandbox.sandbox_types import movable_ancestors


def test_lists_every_directory_between_the_area_root_and_the_path_nearest_first() -> None:
    assert movable_ancestors("/w/a/b/.git/config", ["/w"]) == ["/w/a/b/.git", "/w/a/b", "/w/a"]


def test_the_area_root_itself_is_not_listed() -> None:
    assert movable_ancestors("/w/.git/config", ["/w"]) == ["/w/.git"]
    assert movable_ancestors("/w/.git", ["/w"]) == []


def test_a_sibling_with_the_same_name_prefix_is_not_inside_the_area() -> None:
    assert movable_ancestors("/w2/.git/config", ["/w"]) == []


def test_every_area_counts_and_a_trailing_separator_is_ignored() -> None:
    assert movable_ancestors("/tmp/x/ws/.git/config", ["/w/", "/tmp"]) == ["/tmp/x/ws/.git", "/tmp/x/ws", "/tmp/x"]


def test_a_path_outside_every_area_has_no_movable_ancestor() -> None:
    assert movable_ancestors("/etc/x/y", ["/w"]) == []
