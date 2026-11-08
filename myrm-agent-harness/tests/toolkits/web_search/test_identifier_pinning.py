"""Exact-phrase pinning of CVE ids and DOIs (processing/identifier_pinning.py).

[POS]
Unit tests for pin_structured_identifiers: what it quotes, what it leaves alone.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.web_search.processing.identifier_pinning import pin_structured_identifiers


class TestCve:
    def test_wraps_the_id_in_double_quotes(self) -> None:
        assert (
            pin_structured_identifiers("Explain CVE-2024-38077 exploit and mitigation")
            == 'Explain "CVE-2024-38077" exploit and mitigation'
        )

    def test_lowercase_id_is_written_in_canonical_case(self) -> None:
        assert pin_structured_identifiers("what is cve-2024-1234") == 'what is "CVE-2024-1234"'

    def test_every_occurrence_is_wrapped_once(self) -> None:
        assert (
            pin_structured_identifiers("CVE-2024-1111 vs CVE-2024-1111 patch")
            == '"CVE-2024-1111" vs "CVE-2024-1111" patch'
        )

    def test_already_double_quoted_id_is_not_quoted_again(self) -> None:
        query = 'Analyze "CVE-2023-1234" patch'
        assert pin_structured_identifiers(query) == query


class TestDoi:
    def test_wraps_the_doi_in_double_quotes(self) -> None:
        assert (
            pin_structured_identifiers("What is the result of 10.1038/s41586-024-07487-w paper?")
            == 'What is the result of "10.1038/s41586-024-07487-w" paper?'
        )

    def test_already_single_quoted_identifiers_are_left_as_written(self) -> None:
        query = "check 'cve-2024-1234' and '10.1234/test.doi'"
        assert pin_structured_identifiers(query) == query


class TestMixedAndUnaffected:
    def test_cve_and_doi_in_a_chinese_query_are_both_pinned(self) -> None:
        pinned = pin_structured_identifiers("请分析 CVE-2024-38077 漏洞与 10.1038/s41586-024-07487-w 论文的关系")

        assert '"CVE-2024-38077"' in pinned
        assert '"10.1038/s41586-024-07487-w"' in pinned

    @pytest.mark.parametrize(
        "query",
        [
            "",
            "   ",
            "how to cook pasta",
            "NVDA stock price and revenue growth",
            "TSLA stock price today",
            "famous movie quotes about time",
            "请分析 AAPL 股价走势",
        ],
    )
    def test_queries_without_cve_or_doi_are_returned_unchanged(self, query: str) -> None:
        """Entity names such as tickers are never pinned: their spelling is not an identity."""
        assert pin_structured_identifiers(query) == query


class TestEachIdentifierIsJudgedWhereItStands:
    def test_a_doi_that_prefixes_another_does_not_rewrite_it(self) -> None:
        assert (
            pin_structured_identifiers("10.1000/xyz123 vs 10.1000/xyz1234") == '"10.1000/xyz123" vs "10.1000/xyz1234"'
        )

    def test_repeats_in_any_case_are_all_pinned_in_canonical_case(self) -> None:
        assert pin_structured_identifiers("CVE-2024-3094 cve-2024-3094") == '"CVE-2024-3094" "CVE-2024-3094"'

    def test_an_unquoted_repeat_is_pinned_beside_a_quoted_one(self) -> None:
        assert pin_structured_identifiers("'CVE-2024-1234' vs CVE-2024-1234") == "'CVE-2024-1234' vs \"CVE-2024-1234\""

    @pytest.mark.parametrize(
        "url",
        ["https://doi.org/10.1000/xyz123", "https://nvd.nist.gov/vuln/detail/CVE-2024-3094"],
    )
    def test_an_identifier_inside_a_url_is_left_alone(self, url: str) -> None:
        assert pin_structured_identifiers(f"summarize {url}") == f"summarize {url}"

    def test_sentence_punctuation_stays_outside_the_quotes(self) -> None:
        assert pin_structured_identifiers("read 10.1038/s41586-024-07487-w.") == 'read "10.1038/s41586-024-07487-w".'
        assert pin_structured_identifiers("(CVE-2024-1234) fixed") == '("CVE-2024-1234") fixed'


class TestQuotedPhrasesStayAsWritten:
    @pytest.mark.parametrize(
        "query",
        [
            '"exploit for CVE-2022-22965 mitigation" notes',
            '"xz backdoor CVE-2024-3094" analysis',
            'see "doi 10.1038/nature12373 paper" for details',
        ],
    )
    def test_an_identifier_inside_a_quoted_phrase_is_not_quoted_again(self, query: str) -> None:
        assert pin_structured_identifiers(query) == query

    def test_identifiers_outside_the_phrases_are_still_pinned(self) -> None:
        assert (
            pin_structured_identifiers(
                '"exploit for CVE-2022-22965 mitigation" and CVE-2021-44228 vs "poc CVE-2021-44228"'
            )
            == '"exploit for CVE-2022-22965 mitigation" and "CVE-2021-44228" vs "poc CVE-2021-44228"'
        )


class TestIdentifierNextToOtherText:
    @pytest.mark.parametrize(
        ("query", "pinned"),
        [
            ("分析CVE-2024-3094漏洞原理", '分析"CVE-2024-3094"漏洞原理'),
            ("请解读10.1038/nature14539这篇论文", '请解读"10.1038/nature14539"这篇论文'),
        ],
    )
    def test_an_identifier_written_without_spaces_between_chinese_words_is_pinned(
        self, query: str, pinned: str
    ) -> None:
        assert pin_structured_identifiers(query) == pinned

    @pytest.mark.parametrize(
        "query",
        ["XCVE-2024-3094", "CVE-2024-3094a", "CVE-2024-30941234567", "x10.1038/nature14539"],
    )
    def test_an_identifier_that_continues_into_an_ascii_word_is_left_alone(self, query: str) -> None:
        assert pin_structured_identifiers(query) == query
