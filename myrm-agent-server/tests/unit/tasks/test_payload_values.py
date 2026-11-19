"""Typed reads of the loosely typed task payload snapshot."""

from __future__ import annotations

import pytest

from app.tasks.payload_values import optional_bool, optional_int, optional_str, str_list


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("  gpt-image-2.6-sunburst ", "gpt-image-2.6-sunburst"),
        ("x", "x"),
        ("", None),
        ("   ", None),
        (None, None),
        (7, None),
        (["a"], None),
        (b"bytes", None),
    ],
)
def test_optional_str_keeps_only_a_non_blank_string_stripped(value: object, expected: str | None) -> None:
    assert optional_str(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (["media://a", "  /work/b.png  "], ["media://a", "/work/b.png"]),
        (["", "   ", "media://a"], ["media://a"]),
        (["media://a", 3, None, ["nested"]], ["media://a"]),
        ([], []),
        (None, []),
        ("media://a", []),
        (("media://a",), []),
        ({"a": 1}, []),
    ],
)
def test_str_list_keeps_the_non_blank_strings_of_a_list_only(value: object, expected: list[str]) -> None:
    assert str_list(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(3, 3), (0, 0), (-1, -1), (True, None), (False, None), (2.0, None), ("3", None), (None, None)],
)
def test_optional_int_rejects_a_bool_even_though_it_is_an_int(value: object, expected: int | None) -> None:
    assert optional_int(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [(True, True), (False, False), (1, None), (0, None), ("true", None), (None, None)],
)
def test_optional_bool_accepts_only_a_real_bool(value: object, expected: bool | None) -> None:
    assert optional_bool(value) is expected
