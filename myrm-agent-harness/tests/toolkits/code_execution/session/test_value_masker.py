"""Exact-value masking hides a delivered credential wherever the reads were cut.

The reference below is masking the whole output in one piece: at each position the longest value that starts there is
replaced. A stream, however it is cut, must come out the same.
"""

from __future__ import annotations

import itertools
import random

import pytest

from myrm_agent_harness.toolkits.code_execution.session.value_masker import (
    MASK,
    MIN_MASKED_LENGTH,
    ValueMasker,
    printed_forms,
)


def _one_piece(text: str, values: list[str]) -> str:
    """Independent reference: leftmost position first, longest value first."""
    ordered = sorted((v for v in values if len(v) >= MIN_MASKED_LENGTH), key=len, reverse=True)
    out: list[str] = []
    i = 0
    while i < len(text):
        hit = next((v for v in ordered if text.startswith(v, i)), None)
        if hit is None:
            out.append(text[i])
            i += 1
        else:
            out.append(MASK)
            i += len(hit)
    return "".join(out)


def _streamed(chunks: list[str], values: list[str]) -> str:
    masker = ValueMasker(values)
    return "".join(masker.feed(chunk) for chunk in chunks) + masker.flush()


class TestMasking:
    def test_value_is_replaced(self) -> None:
        assert _streamed(["token is hunter2 now"], ["hunter2"]) == f"token is {MASK} now"

    def test_every_occurrence_is_replaced(self) -> None:
        assert _streamed(["hunter2 and hunter2"], ["hunter2"]) == f"{MASK} and {MASK}"

    def test_text_without_a_value_is_untouched(self) -> None:
        assert _streamed(["nothing to hide here\n"], ["hunter2"]) == "nothing to hide here\n"

    def test_regex_metacharacters_in_a_value_are_literal(self) -> None:
        value = "a.b*c+d?(e)[f]{g}|h^i$j\\k"
        assert _streamed([f"x {value} y", "a-b-c"], [value]) == f"x {MASK} ya-b-c"

    def test_multibyte_value(self) -> None:
        assert _streamed(["密码是 pässwörd-密钥 ok"], ["pässwörd-密钥"]) == f"密码是 {MASK} ok"

    def test_longest_value_wins_where_values_overlap(self) -> None:
        assert _streamed(["abcdef!"], ["abcd", "abcdef"]) == f"{MASK}!"

    def test_a_value_inside_another_is_masked_once(self) -> None:
        assert _streamed(["xx-secret-token-yy"], ["secret", "secret-token"]) == f"xx-{MASK}-yy"

    def test_values_shorter_than_the_minimum_are_left_alone(self) -> None:
        short = "x" * (MIN_MASKED_LENGTH - 1)
        assert _streamed([f"a {short} b"], [short]) == f"a {short} b"

    def test_no_value_means_no_work_and_no_holding(self) -> None:
        masker = ValueMasker(["", "ab"])
        assert masker.feed("abab") == "abab"
        assert masker.flush() == ""


class TestSplitReads:
    @pytest.mark.parametrize("cut", range(1, len("before hunter2 after")))
    def test_cut_at_every_position(self, cut: int) -> None:
        text = "before hunter2 after"
        assert _streamed([text[:cut], text[cut:]], ["hunter2"]) == f"before {MASK} after"

    def test_value_arriving_one_character_at_a_time(self) -> None:
        text = "a hunter2 b hunter2"
        assert _streamed(list(text), ["hunter2"]) == f"a {MASK} b {MASK}"

    def test_a_read_ending_in_the_start_of_a_value_is_held(self) -> None:
        masker = ValueMasker(["hunter2"])
        assert masker.feed("pass hun") == "pass "
        assert masker.feed("ter2!") == f"{MASK}!"

    def test_a_held_start_that_turns_out_ordinary_is_released(self) -> None:
        masker = ValueMasker(["hunter2"])
        assert masker.feed("a hun") == "a "
        assert masker.feed("gry") == "hungry"

    def test_what_is_held_is_bounded_by_the_longest_value(self) -> None:
        masker = ValueMasker(["hunter2"])
        released = masker.feed("x" * 1000 + "hunt")
        assert released == "x" * 1000
        assert masker.flush() == "hunt"

    def test_a_shorter_value_is_not_released_while_a_longer_one_may_follow(self) -> None:
        masker = ValueMasker(["abcd", "abcdef"])
        assert masker.feed("abcd") == ""
        assert masker.feed("ef") == MASK

    def test_a_shorter_value_is_masked_once_the_longer_one_cannot_follow(self) -> None:
        masker = ValueMasker(["abcd", "abcdef"])
        assert masker.feed("abcd") == ""
        assert masker.feed("x") == f"{MASK}x"

    def test_a_complete_value_at_the_end_is_masked_at_the_flush(self) -> None:
        masker = ValueMasker(["abcd", "abcdef"])
        assert masker.feed("abcd") == ""
        assert masker.flush() == MASK

    def test_a_stream_that_ends_inside_a_value_releases_the_fragment(self) -> None:
        masker = ValueMasker(["hunter2"])
        assert masker.feed("pass hunt") == "pass "
        assert masker.flush() == "hunt"
        assert masker.flush() == ""


class TestEqualsMaskingInOnePiece:
    def test_every_cut_of_overlapping_values(self) -> None:
        values = ["abab", "ababba", "bbaa", "aabbaa"]
        texts = ["xababbaay", "aabbaabab", "ababab", "babbaab", "abababba", "aaabbaabbaa"]
        for text in texts:
            expected = _one_piece(text, values)
            for cut in range(len(text) + 1):
                assert _streamed([text[:cut], text[cut:]], values) == expected, (text, cut)

    def test_random_streams_cut_at_random_places(self) -> None:
        rng = random.Random(20261028)
        values = ["abab", "ababba", "bbaa", "aabbaa", "cabc"]
        for _ in range(3000):
            text = "".join(rng.choice("abc") for _ in range(rng.randint(0, 60)))
            cuts = sorted(rng.sample(range(len(text) + 1), k=min(len(text) + 1, rng.randint(0, 5))))
            chunks = [text[a:b] for a, b in itertools.pairwise([0, *cuts, len(text)])]
            assert _streamed(chunks, values) == _one_piece(text, values), (text, chunks)


_AWKWARD = 'p@ss w/rd%1&"x\\y'
_AWKWARD_URL = "p%40ss%20w%2Frd%251%26%22x%5Cy"
_AWKWARD_JSON = 'p@ss w/rd%1&\\"x\\\\y'


class TestPrintedForms:
    def test_a_plain_token_has_no_other_form(self) -> None:
        assert printed_forms(["correct-horse-battery_staple.9"]) == ["correct-horse-battery_staple.9"]

    def test_a_password_with_special_characters_also_has_its_url_and_json_forms(self) -> None:
        assert set(printed_forms([_AWKWARD])) == {_AWKWARD, _AWKWARD_URL, _AWKWARD_JSON}

    def test_a_multi_line_secret_has_the_forms_a_key_takes_in_a_url_or_a_json_string(self) -> None:
        forms = printed_forms(["-----BEGIN KEY-----\nabc\n-----END KEY-----"])

        assert "-----BEGIN%20KEY-----%0Aabc%0A-----END%20KEY-----" in forms
        assert "-----BEGIN KEY-----\\nabc\\n-----END KEY-----" in forms

    def test_non_ascii_is_percent_encoded_as_utf8_and_stays_readable_in_json(self) -> None:
        assert set(printed_forms(["pässwort1"])) == {"pässwort1", "p%C3%A4sswort1"}

    def test_url_encoders_that_leave_the_punctuation_bare_are_covered(self) -> None:
        assert set(printed_forms(["p@ss!1(x)"])) == {"p@ss!1(x)", "p%40ss%211%28x%29", "p%40ss!1(x)"}

    def test_a_value_under_the_minimum_has_no_forms_at_all(self) -> None:
        assert printed_forms(["a@b"]) == []

    def test_the_same_form_of_two_values_is_listed_once(self) -> None:
        assert printed_forms(["abcd1234", "abcd1234"]) == ["abcd1234"]


class TestMaskingTheForms:
    _TEXT = f'curl https://u:{_AWKWARD_URL}@h/ -d \'{{"p":"{_AWKWARD_JSON}"}}\' raw={_AWKWARD}'
    _MASKED = f'curl https://u:{MASK}@h/ -d \'{{"p":"{MASK}"}}\' raw={MASK}'

    def test_every_form_is_hidden(self) -> None:
        assert _streamed([self._TEXT], printed_forms([_AWKWARD])) == self._MASKED

    @pytest.mark.parametrize("cut", range(len(_TEXT) + 1))
    def test_every_form_is_hidden_wherever_the_read_was_cut(self, cut: int) -> None:
        assert _streamed([self._TEXT[:cut], self._TEXT[cut:]], printed_forms([_AWKWARD])) == self._MASKED
