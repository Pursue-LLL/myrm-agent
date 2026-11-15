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


def _pruned(extra_blocks: str) -> str:
    """一篇有正文的文章，加上待判定的块，返回剪枝后的 HTML"""
    html = (
        "<html><body><article><p>This is an important article. It contains a lot of very useful information.</p>"
        f"{extra_blocks}</article></body></html>"
    )
    return "".join(ContentPruningFilter().filter_content(html))


@pytest.mark.parametrize(
    "classes",
    [
        "hidden",
        "flex hidden",
        "hidden-xs",
        "is-hidden-mobile",
        "sm:hidden",
        "md:hidden",
        "lg:hidden",
        "xl:hidden",
        "2xl:hidden",
    ],
)
def test_content_hidden_for_every_viewer_or_by_breakpoint_is_pruned(classes: str) -> None:
    """恒隐藏的块与只在小屏出现的副本不是正文，剪掉"""
    kept = _pruned(f'<div class="{classes}"><p>Mobile menu copy of the page links.</p></div>')

    assert "important article" in kept
    assert "Mobile menu copy" not in kept


@pytest.mark.parametrize(
    "classes",
    [
        "dark:hidden",
        "group-hover:hidden",
        "peer-checked:hidden",
        "md:dark:hidden",
        "data-[state=closed]:hidden",
        "print:hidden",
    ],
)
def test_content_hidden_only_by_a_state_variant_is_kept(classes: str) -> None:
    """主题、指针与状态变体的 hidden 只是当下不显示，里面是真实内容，不能剪"""
    kept = _pruned(f'<div class="{classes}"><p>Install it with pip install example-package today.</p></div>')

    assert "pip install example-package" in kept


def test_a_dual_theme_code_block_keeps_the_light_copy_only() -> None:
    """文档站为两种主题各渲染一份代码：恒隐藏的那份剪掉，另一份保留，代码不会整块消失"""
    kept = _pruned(
        '<pre class="dark:hidden"><code>print("light theme copy")</code></pre>'
        '<pre class="hidden dark:block"><code>print("dark theme copy")</code></pre>'
    )

    assert "light theme copy" in kept
    assert "dark theme copy" not in kept


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
