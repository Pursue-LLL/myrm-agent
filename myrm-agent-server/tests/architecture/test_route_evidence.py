"""The evidence of a registered external route consumer must name the route it justifies.

[POS]
tests/architecture/test_route_evidence.py

[INPUT]
- tests.support.route_evidence: the citation parser and the check of one entry against a checkout

[OUTPUT]
- Pins what counts as evidence that still holds: the cited lines spell the route's last static segment as a whole
  word, or contain the anchor the entry names; a missing file or a line past the end fails; a tree the checkout
  lacks is skipped and reported as skipped

The registry itself is checked by test_api_route_consumers.py::test_external_consumer_evidence_still_names_the_route.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.support.route_evidence import Citation, EvidenceCheck, check_evidence, parse_citation, route_word


@pytest.fixture
def checkout(tmp_path: Path) -> Path:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "caller.py").write_text(
        "\n".join(
            [
                "import httpx",
                'DRAIN = "/api/v1/system/drain"',
                'headers = {"X-Request": "1"}',
                '<form method="post" action="">',
                "tail",
            ]
        ),
        encoding="utf-8",
    )
    return tmp_path


def _check(checkout: Path, route: str, evidence: str) -> EvidenceCheck:
    method, path = route.split(" ", 1)
    return check_evidence(method, path, evidence, roots=(checkout,))


def test_a_cited_line_that_spells_the_route_holds(checkout: Path) -> None:
    assert _check(checkout, "POST /system/drain", "recycler drains first (svc/caller.py:2)") == EvidenceCheck()


def test_a_range_holds_when_any_line_in_it_spells_the_route(checkout: Path) -> None:
    assert _check(checkout, "POST /system/drain", "recycler drains first (svc/caller.py:1-3)") == EvidenceCheck()


def test_a_line_that_no_longer_names_the_route_fails(checkout: Path) -> None:
    check = _check(checkout, "GET /memory/head", "probe for clients (svc/caller.py:1)")
    assert check.problem is not None and "does not spell `head`" in check.problem


def test_the_route_word_must_be_a_whole_word(checkout: Path) -> None:
    # line 3 holds `headers`: it contains `head` but is a different word
    check = _check(checkout, "GET /memory/head", "probe (svc/caller.py:3)")
    assert check.problem is not None


def test_params_are_not_the_route_word(checkout: Path) -> None:
    assert _check(checkout, "GET /system/drain/{id}", "caller (svc/caller.py:2)") == EvidenceCheck()


def test_a_route_of_params_only_needs_an_anchor(checkout: Path) -> None:
    check = _check(checkout, "POST /{token}", "form (svc/caller.py:4)")
    assert check.problem is not None and "anchor" in check.problem


def test_an_anchor_replaces_the_route_word(checkout: Path) -> None:
    evidence = '<form method="post" action="">'
    assert _check(checkout, "POST /{token}", f"unlock form (svc/caller.py:4 `{evidence}`)") == EvidenceCheck()


def test_an_anchor_that_moved_away_fails(checkout: Path) -> None:
    check = _check(checkout, "POST /{token}", "unlock form (svc/caller.py:2 `<form`)")
    assert check.problem is not None and "does not contain `<form`" in check.problem


def test_a_line_past_the_end_of_the_file_fails(checkout: Path) -> None:
    check = _check(checkout, "POST /system/drain", "caller (svc/caller.py:99)")
    assert check.problem is not None and "past the end" in check.problem


def test_a_missing_file_in_a_present_tree_fails(checkout: Path) -> None:
    check = _check(checkout, "POST /system/drain", "caller (svc/gone.py:2)")
    assert check.problem is not None and "does not exist" in check.problem


def test_a_tree_the_checkout_lacks_is_skipped_not_passed(checkout: Path) -> None:
    assert _check(checkout, "POST /system/drain", "caller (other-repo/x.py:2)") == EvidenceCheck(skipped=True)


def test_evidence_without_a_citation_fails(checkout: Path) -> None:
    assert _check(checkout, "POST /system/drain", "the control plane calls it").problem is not None


def test_a_backwards_range_fails(checkout: Path) -> None:
    assert _check(checkout, "POST /system/drain", "caller (svc/caller.py:3-1)").problem is not None


def test_a_later_root_resolves_what_an_earlier_one_lacks(checkout: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    empty = tmp_path_factory.mktemp("oss")
    check = check_evidence("POST", "/system/drain", "caller (svc/caller.py:2)", roots=(empty, checkout))
    assert check == EvidenceCheck()


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ("who (a/b.py:12)", Citation("a/b.py", 12, 12, None)),
        ("who (a/b.py:12-15)", Citation("a/b.py", 12, 15, None)),
        ("who (a/b.py:12 `x = 1`)", Citation("a/b.py", 12, 12, "x = 1")),
        ("who (a/b.py)", None),
        ("who (a/b.py:12) and more", None),
    ],
)
def test_parse_citation(evidence: str, expected: Citation | None) -> None:
    assert parse_citation(evidence) == expected


@pytest.mark.parametrize(
    ("path", "word"),
    [("/memory/head", "head"), ("/public/artifact-share/{token}/{asset_path}", "artifact-share"), ("/{token}", None)],
)
def test_route_word(path: str, word: str | None) -> None:
    assert route_word(path) == word
