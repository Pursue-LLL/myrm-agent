"""ContentPruningFilter 测试"""

import pytest

from myrm_agent_harness.toolkits.web_fetch.processing.content_pruning import ContentPruningFilter


def test_filter_initialization():
    """测试过滤器初始化"""
    filter = ContentPruningFilter()

    assert filter.threshold > 0
    assert filter.min_word_threshold >= 0
    assert "text_density" in filter.metric_weights


def test_filter_simple_content():
    """测试简单内容过滤"""
    filter = ContentPruningFilter()

    assert filter.threshold > 0
    assert len(filter.excluded_tags) > 0


def test_filter_with_threshold():
    """测试自定义阈值"""
    filter_strict = ContentPruningFilter(threshold=0.7)
    filter_loose = ContentPruningFilter(threshold=0.3)

    assert filter_strict.threshold > filter_loose.threshold


def test_filter_with_min_words():
    """测试最小字数阈值"""
    filter = ContentPruningFilter(min_word_threshold=10)

    assert filter.min_word_threshold == 10


def test_filter_content_keeps_the_article_and_drops_navigation_and_footer():
    """正文保留，导航与页脚被剪掉"""
    html_content = """
    <html>
        <body>
            <article>This is an important article. It contains a lot of very useful information.</article>
            <nav>Some links</nav>
            <footer>Copyright 2026</footer>
        </body>
    </html>
    """

    joined = "".join(ContentPruningFilter().filter_content(html_content))

    assert "This is an important article" in joined
    assert "Some links" not in joined
    assert "Copyright 2026" not in joined


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
