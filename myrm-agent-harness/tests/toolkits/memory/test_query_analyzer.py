"""Unit tests for query_analyzer module (bilingual query analysis)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from myrm_agent_harness.toolkits.memory._internal.temporal_window import derive_temporal_window
from myrm_agent_harness.toolkits.memory.query_analyzer import (
    QueryContext,
    analyze_query,
    contains_person_name,
    contains_quoted_phrase,
    extract_person_names,
    extract_quoted_phrases,
    is_assistant_reference_query,
    is_preference_query,
)


class TestExtractQuotedPhrases:
    """Test quoted phrase extraction."""

    def test_double_quotes(self) -> None:
        assert extract_quoted_phrases('Find "hello world" please') == ["hello world"]

    def test_single_quotes(self) -> None:
        assert extract_quoted_phrases("Find 'hello world' please") == ["hello world"]

    def test_chinese_quotes(self) -> None:
        assert extract_quoted_phrases("搜索「你好世界」的内容") == ["你好世界"]

    def test_multiple_quotes(self) -> None:
        result = extract_quoted_phrases('"first phrase" and "second phrase"')
        assert "first phrase" in result
        assert "second phrase" in result

    def test_short_phrases_filtered(self) -> None:
        assert extract_quoted_phrases('"ab"') == []
        assert extract_quoted_phrases('"a"') == []

    def test_no_quotes(self) -> None:
        assert extract_quoted_phrases("no quotes here") == []

    def test_empty_string(self) -> None:
        assert extract_quoted_phrases("") == []

    def test_mixed_quote_types(self) -> None:
        result = extract_quoted_phrases("""He said "hello world" and '你好世界'""")
        assert "hello world" in result
        assert "你好世界" in result


class TestExtractPersonNames:
    """Test person name extraction."""

    def test_basic_name(self) -> None:
        assert "John" in extract_person_names("Ask John about this")

    def test_multiple_names(self) -> None:
        result = extract_person_names("Tell Mary and Bob about it")
        assert "Mary" in result
        assert "Bob" in result

    def test_sentence_start_ignored(self) -> None:
        assert extract_person_names("Hello world") == []

    def test_common_words_excluded(self) -> None:
        result = extract_person_names("Ask He and She about Monday")
        assert "He" not in result
        assert "She" not in result
        assert "Monday" not in result

    def test_no_names(self) -> None:
        assert extract_person_names("tell me about python") == []

    def test_empty_string(self) -> None:
        assert extract_person_names("") == []

    def test_punctuation_stripped(self) -> None:
        assert "Alice" in extract_person_names("Ask Alice, please")


# Thursday afternoon: calendar edges below are deterministic.
NOW = datetime(2026, 11, 12, 15, 0, tzinfo=UTC)

# Phrase → (matched marker, proximity anchor); the anchor is the shared temporal
# rules' output, so these also pin the hard-filter window the same phrase gets.
ANCHORED_PHRASES = [
    ("Tell me about yesterday", "yesterday", datetime(2026, 11, 11, 12, 0, tzinfo=UTC)),
    ("What happened today", "today", datetime(2026, 11, 12, 12, 0, tzinfo=UTC)),
    ("昨天讨论的方案", "昨天", datetime(2026, 11, 11, 12, 0, tzinfo=UTC)),
    ("前天你说的那个事情", "前天", datetime(2026, 11, 10, 12, 0, tzinfo=UTC)),
    ("今天有什么安排", "今天", datetime(2026, 11, 12, 12, 0, tzinfo=UTC)),
    # Last week is Mon 11-02 .. Sun 11-08: its center is Thursday noon.
    ("Show me last week stuff", "last week", datetime(2026, 11, 5, 12, 0, tzinfo=UTC)),
    ("上周的会议内容", "上周", datetime(2026, 11, 5, 12, 0, tzinfo=UTC)),
    ("上上周的周报", "上上周", datetime(2026, 10, 29, 12, 0, tzinfo=UTC)),
    ("上个月的报告", "上个月", datetime(2026, 10, 16, 12, 0, tzinfo=UTC)),
    ("上上个月的账单", "上上个月", datetime(2026, 9, 16, 0, 0, tzinfo=UTC)),
    ("去年的项目", "去年", datetime(2025, 7, 2, 12, 0, tzinfo=UTC)),
    # Relative points anchor on the point itself; Chinese numerals resolve too.
    ("Something from 3 days ago", "3 days ago", NOW - timedelta(days=3)),
    ("From 2 weeks ago", "2 weeks ago", NOW - timedelta(weeks=2)),
    ("5天前你提到的", "5天前", NOW - timedelta(days=5)),
    ("2周前的代码", "2周前", NOW - timedelta(weeks=2)),
    ("3个月前的设计", "3个月前", NOW - timedelta(days=90)),
    ("三天前的会议", "三天前", NOW - timedelta(days=3)),
    ("两周前的决定", "两周前", NOW - timedelta(weeks=2)),
    # Recency markers center on now: nearer is better.
    ("最近学到的东西", "最近", NOW),
    ("最近三天的改动", "最近三天", NOW),
]


class TestTemporalReference:
    """Marker and proximity anchor resolved by the shared temporal rules."""

    @pytest.mark.parametrize(("query", "marker", "anchor"), ANCHORED_PHRASES)
    def test_marker_and_anchor(self, query: str, marker: str, anchor: datetime) -> None:
        ctx = analyze_query(query, now=NOW)
        assert ctx.temporal_markers == [marker]
        assert ctx.reference_time == anchor

    @pytest.mark.parametrize("query", ["本周的计划", "这个月的账单", "今年的目标", "this week's plan"])
    def test_current_period_has_marker_but_no_anchor(self, query: str) -> None:
        # The period still contains now: no past point to center on.
        ctx = analyze_query(query, now=NOW)
        assert len(ctx.temporal_markers) == 1
        assert ctx.reference_time is None

    @pytest.mark.parametrize("query", [phrase for phrase, _, _ in ANCHORED_PHRASES])
    def test_anchor_lies_inside_hard_filter_window(self, query: str) -> None:
        # Soft proximity and the collect-stage hard filter must agree on the period.
        window = derive_temporal_window(query, now=NOW)
        ctx = analyze_query(query, now=NOW)
        assert window is not None
        assert ctx.reference_time is not None
        assert window.since <= ctx.reference_time <= window.until

    def test_stacked_prefix_is_not_read_as_single_step(self) -> None:
        single = analyze_query("上周的周报", now=NOW).reference_time
        stacked = analyze_query("上上周的周报", now=NOW).reference_time
        assert single is not None
        assert stacked == single - timedelta(weeks=1)

    def test_first_rule_wins_when_several_markers_present(self) -> None:
        ctx = analyze_query("yesterday and last week", now=NOW)
        assert ctx.temporal_markers == ["yesterday"]
        assert ctx.reference_time == datetime(2026, 11, 11, 12, 0, tzinfo=UTC)

    @pytest.mark.parametrize("query", ["What is machine learning", "", "明天的安排", "next week we deploy"])
    def test_no_past_marker(self, query: str) -> None:
        ctx = analyze_query(query, now=NOW)
        assert ctx.temporal_markers == []
        assert ctx.reference_time is None


class TestContainsQuotedPhrase:
    """Test quoted phrase matching."""

    def test_exact_match(self) -> None:
        assert contains_quoted_phrase("Hello World is great", "hello world") is True

    def test_case_insensitive(self) -> None:
        assert contains_quoted_phrase("HELLO WORLD", "hello world") is True

    def test_not_found(self) -> None:
        assert contains_quoted_phrase("something else", "hello world") is False


class TestContainsPersonName:
    """Test person name matching."""

    def test_word_boundary(self) -> None:
        assert contains_person_name("Ask John about it", "John") is True

    def test_case_insensitive(self) -> None:
        assert contains_person_name("ask john about it", "John") is True

    def test_partial_no_match(self) -> None:
        assert contains_person_name("Johnny is here", "John") is False

    def test_not_found(self) -> None:
        assert contains_person_name("nothing here", "Alice") is False


class TestIsAssistantReferenceQuery:
    """Test assistant-reference query detection (English and Chinese)."""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("What did you suggest for testing?", True),
            ("You told me to use pytest", True),
            ("You mentioned this earlier", True),
            ("You recommended a library", True),
            ("Remind me what you said", True),
            ("You provided some examples", True),
            ("You listed three options", True),
            ("You gave me a code snippet", True),
            ("You described the architecture", True),
            ("What did you tell me about databases?", True),
            ("You came up with a good idea", True),
            ("You helped me debug this", True),
            ("You explained the algorithm", True),
            ("Can you remind me your suggestion?", True),
            ("You identified the issue", True),
            ("You said it was a bug", True),
            ("What is machine learning?", False),
            ("Tell me about Python", False),
            ("How do I install npm?", False),
            ("user asked me a question", False),
            ("Someone suggested using Docker", False),
            ("The docs say to do this", False),
        ],
    )
    def test_english_patterns(self, query: str, expected: bool) -> None:
        assert is_assistant_reference_query(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("你建议用什么框架?", True),
            ("你说过这个方案不行", True),
            ("你之前提到过这个问题", True),
            ("你提到的那个库叫什么", True),
            ("你帮我调试过的代码", True),
            ("你推荐的那个工具", True),
            ("你给我写的代码", True),
            ("你解释过的算法", True),
            ("你说的那个方法", True),
            ("你提供的示例", True),
            ("你列的三个选项", True),
            ("提醒我你之前说的", True),
            ("什么是机器学习?", False),
            ("告诉我关于Python的事", False),
        ],
    )
    def test_chinese_patterns(self, query: str, expected: bool) -> None:
        assert is_assistant_reference_query(query) == expected

    def test_case_insensitive(self) -> None:
        assert is_assistant_reference_query("YOU TOLD ME SOMETHING")
        assert is_assistant_reference_query("What Did You Suggest?")

    def test_empty_and_edge_cases(self) -> None:
        assert not is_assistant_reference_query("")
        assert not is_assistant_reference_query("   ")
        assert not is_assistant_reference_query("\\n\\t")


class TestIsPreferenceQuery:
    """Test preference query detection (English and Chinese)."""

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("What do I like for breakfast?", True),
            ("My favorite color?", True),
            ("What do I usually do?", True),
            ("What am I interested in?", True),
            ("What do I dislike?", True),
            ("What do I hate?", True),
            ("What do I want?", True),
            ("What do I need?", True),
            ("What have I been working on?", True),
            ("Remind me what I like", True),
            ("my habit of coding", True),
            ("my belief about AI", True),
            ("my goal this year", True),
            ("Tell me about Python", False),
            ("How do I install npm?", False),
            ("What is machine learning?", False),
        ],
    )
    def test_english_patterns(self, query: str, expected: bool) -> None:
        assert is_preference_query(query) == expected

    @pytest.mark.parametrize(
        "query,expected",
        [
            ("我喜欢什么颜色?", True),
            ("我的偏好是什么?", True),
            ("我通常怎么做?", True),
            ("我习惯用vim", True),
            ("我想要学什么?", True),
            ("我倾向于用Python", True),
            ("我的习惯是什么?", True),
            ("我的目标是什么?", True),
            ("我喜欢用什么编辑器?", True),
            ("我偏好暗色主题", True),
            ("我讨厌写文档", True),
            ("我不喜欢JavaScript", True),
            ("什么是机器学习?", False),
            ("如何安装Python?", False),
        ],
    )
    def test_chinese_patterns(self, query: str, expected: bool) -> None:
        assert is_preference_query(query) == expected


class TestAnalyzeQuery:
    """Test the full analyze_query integration."""

    def test_english_temporal_query(self) -> None:
        ctx = analyze_query("What did John say yesterday?")
        assert isinstance(ctx, QueryContext)
        assert "John" in ctx.person_names
        assert any("yesterday" in m for m in ctx.temporal_markers)
        assert ctx.reference_time is not None

    def test_chinese_temporal_query(self) -> None:
        ctx = analyze_query("昨天讨论的方案是什么")
        assert any("昨天" in m for m in ctx.temporal_markers)
        assert ctx.reference_time is not None

    def test_quoted_phrase_query(self) -> None:
        ctx = analyze_query('Search for "machine learning" articles')
        assert "machine learning" in ctx.quoted_phrases

    def test_preference_query(self) -> None:
        ctx = analyze_query("What do I like for breakfast?")
        assert ctx.is_preference_query is True

    def test_non_preference_query(self) -> None:
        ctx = analyze_query("What is Python?")
        assert ctx.is_preference_query is False

    def test_combined_signals(self) -> None:
        ctx = analyze_query("""Tell Bob about "best practices" from last week""")
        assert "Bob" in ctx.person_names
        assert "best practices" in ctx.quoted_phrases
        assert len(ctx.temporal_markers) > 0
        assert ctx.reference_time is not None

    def test_empty_query(self) -> None:
        ctx = analyze_query("")
        assert ctx.quoted_phrases == []
        assert ctx.person_names == []
        assert ctx.temporal_markers == []
        assert ctx.reference_time is None
        assert ctx.is_preference_query is False
