"""Tests for the content-addressed memo behind skill listing.

[INPUT]
- backends.skills._content_memo::ContentMemo, clear_content_memos (POS: the memo under test)

[OUTPUT]
- Fails when a value is served for text that differs by even one byte, when a failed or refused derivation is pinned,
  when memory is not bounded by entry count and text size, when concurrent use corrupts the memo, or when clearing
  leaves an entry behind.

[POS]
Pins the memo's contract in isolation; the scan, frontmatter and token-cost call sites have their own files.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

import pytest

from myrm_agent_harness.backends.skills._content_memo import _MAX_MEMOIZED_CHARS, ContentMemo, clear_content_memos


class _Counter:
    """A derivation that records how often it really ran."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, value: str = "derived") -> str:
        self.calls += 1
        return value


def test_identical_content_is_derived_once() -> None:
    memo = ContentMemo[str]("test")
    compute = _Counter()

    first = memo.get_or_compute("text", compute)
    second = memo.get_or_compute("text", compute)

    assert first == second == "derived"
    assert compute.calls == 1


@pytest.mark.parametrize(
    ("original", "variant"),
    [
        ("line one\nline two\n", "line one\r\nline two\r\n"),
        ("body", "body "),
        ("body", "Body"),
        ("caf\u00e9", "cafe\u0301"),
    ],
    ids=["crlf", "trailing-space", "case", "unicode-normalization"],
)
def test_text_differing_in_a_single_byte_is_a_miss(original: str, variant: str) -> None:
    memo = ContentMemo[str]("test")
    compute = _Counter()

    memo.get_or_compute(original, lambda: compute("a"))
    served = memo.get_or_compute(variant, lambda: compute("b"))

    assert served == "b"
    assert compute.calls == 2


def test_scope_separates_equal_text() -> None:
    memo = ContentMemo[str]("test")
    compute = _Counter()

    memo.get_or_compute("text", lambda: compute("for-a"), scope="a")
    served = memo.get_or_compute("text", lambda: compute("for-b"), scope="b")

    assert served == "for-b"
    assert compute.calls == 2


def test_a_failed_derivation_is_not_pinned() -> None:
    memo = ContentMemo[str]("test")
    attempts = 0

    def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ValueError("first attempt fails")
        return "recovered"

    with pytest.raises(ValueError, match="first attempt fails"):
        memo.get_or_compute("text", flaky)

    assert memo.get_or_compute("text", flaky) == "recovered"
    assert attempts == 2


def test_a_value_the_caller_refuses_is_returned_but_not_stored() -> None:
    memo = ContentMemo[str]("test")
    compute = _Counter()

    first = memo.get_or_compute("text", compute, keep=lambda value: False)
    second = memo.get_or_compute("text", compute, keep=lambda value: False)

    assert first == second == "derived"
    assert compute.calls == 2


def test_text_beyond_the_size_limit_bypasses_the_memo() -> None:
    memo = ContentMemo[str]("test")
    compute = _Counter()
    at_limit = "x" * _MAX_MEMOIZED_CHARS
    beyond_limit = "x" * (_MAX_MEMOIZED_CHARS + 1)

    memo.get_or_compute(at_limit, compute)
    memo.get_or_compute(at_limit, compute)
    memo.get_or_compute(beyond_limit, compute)
    memo.get_or_compute(beyond_limit, compute)

    assert compute.calls == 3, "text at the limit is pinned once; text beyond it is derived every time"


def test_least_recently_used_entry_is_evicted_first() -> None:
    memo = ContentMemo[str]("test", maxsize=3)
    counters = {key: _Counter() for key in "abcd"}

    for key in "abc":
        memo.get_or_compute(key, lambda key=key: counters[key](key))
    memo.get_or_compute("a", lambda: counters["a"]("a"))  # touch: "b" is now the oldest
    memo.get_or_compute("d", lambda: counters["d"]("d"))  # evicts "b"

    for key in "acd":
        memo.get_or_compute(key, lambda key=key: counters[key](key))
    memo.get_or_compute("b", lambda: counters["b"]("b"))

    assert [counters[key].calls for key in "abcd"] == [1, 2, 1, 1]


def test_lone_surrogates_are_still_memoizable() -> None:
    memo = ContentMemo[str]("test")
    compute = _Counter()

    memo.get_or_compute("broken \ud800 text", compute)
    memo.get_or_compute("broken \ud800 text", compute)

    assert compute.calls == 1


def test_concurrent_use_returns_the_right_value_for_every_text() -> None:
    # 40 texts through a 16-entry memo: constant eviction while eight threads read and write.
    memo = ContentMemo[str]("test", maxsize=16)
    texts = [f"text-{index}" for index in range(40)]

    def worker(seed: int) -> list[str]:
        mismatches = []
        for step in range(400):
            text = texts[(seed * 7 + step * 13) % len(texts)]
            if memo.get_or_compute(text, lambda text=text: text.upper()) != text.upper():
                mismatches.append(text)
        return mismatches

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(worker, range(8)))

    assert results == [[]] * 8


def test_clear_content_memos_empties_every_memo() -> None:
    first, second = ContentMemo[str]("first"), ContentMemo[str]("second")
    compute = _Counter()
    first.get_or_compute("text", compute)
    second.get_or_compute("text", compute)

    clear_content_memos()
    first.get_or_compute("text", compute)
    second.get_or_compute("text", compute)

    assert compute.calls == 4
