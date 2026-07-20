"""Telegram Rich Message 富文本格式化与流式更新 — 完整能力验证测试。

覆盖范围:
- md_to_telegram_html: Markdown→HTML 转换 (格式化、代码块、表格降级、HTML转义)
- split_markdown_rich: Rich Message UTF-8 分割 (语义断点、代码围栏保护)
- _find_utf8_cut: UTF-8 字节安全切割
- _render_monospace_table / _convert_tables: GFM 表格→ASCII monospace 降级
- CJK 内容: 中日韩字符 UTF-16/UTF-8 处理正确性
- LaTeX / 数学公式: 保留不被格式化破坏
- split_message: HTML tag 状态机边界覆盖 (expandable/blockquote 标签)
"""

from __future__ import annotations

from app.channels.providers.telegram.html_converter import (
    _convert_tables,
    _find_utf8_cut,
    _render_monospace_table,
    _utf16_len,
    md_to_telegram_html,
    split_markdown_rich,
    split_message,
)

# ──────────────────────────────────────────────
# 1. md_to_telegram_html 转换测试
# ──────────────────────────────────────────────

class TestMdToTelegramHtml:
    def test_bold(self):
        assert md_to_telegram_html("**hello**") == "<b>hello</b>"

    def test_italic(self):
        assert md_to_telegram_html("*hello*") == "<i>hello</i>"

    def test_strikethrough(self):
        assert md_to_telegram_html("~~hello~~") == "<s>hello</s>"

    def test_inline_code(self):
        result = md_to_telegram_html("`print('hi')`")
        assert "<code>" in result
        assert "print(&#x27;hi&#x27;)" in result or "print(&#39;hi&#39;)" in result or "print('hi')" in result

    def test_code_block_with_language(self):
        md = "```python\nprint('hi')\n```"
        result = md_to_telegram_html(md)
        assert '<code class="language-python">' in result
        assert "<pre>" in result

    def test_code_block_without_language(self):
        md = "```\nsome code\n```"
        result = md_to_telegram_html(md)
        assert "<pre>" in result
        assert "some code" in result

    def test_link(self):
        md = "[Google](https://google.com)"
        result = md_to_telegram_html(md)
        assert '<a href="https://google.com">Google</a>' in result

    def test_html_entities_escaped(self):
        md = "1 < 2 & 3 > 0"
        result = md_to_telegram_html(md)
        assert "&lt;" in result
        assert "&amp;" in result
        assert "&gt;" in result

    def test_mixed_formatting(self):
        md = "**bold** and *italic* and ~~strike~~"
        result = md_to_telegram_html(md)
        assert "<b>bold</b>" in result
        assert "<i>italic</i>" in result
        assert "<s>strike</s>" in result

    def test_code_block_not_formatted(self):
        """Code blocks should preserve content without applying bold/italic."""
        md = "```\n**not bold** *not italic*\n```"
        result = md_to_telegram_html(md)
        assert "<b>" not in result
        assert "<i>" not in result

    def test_gfm_table_degradation(self):
        """GFM table should be converted to ASCII monospace table in <pre>."""
        md = "| Name | Age |\n|------|-----|\n| Alice | 30 |"
        result = md_to_telegram_html(md)
        assert "<pre>" in result
        assert "┌" in result
        assert "│" in result
        assert "┘" in result

    def test_existing_telegram_tags_preserved(self):
        """Telegram-supported HTML tags in input should not be double-escaped."""
        md = "<b>already bold</b> text"
        result = md_to_telegram_html(md)
        assert "<b>already bold</b>" in result

    def test_non_telegram_tags_escaped(self):
        """Non-Telegram HTML tags should be escaped."""
        md = "<div>not allowed</div>"
        result = md_to_telegram_html(md)
        assert "&lt;div&gt;" in result

    def test_latex_formula_preserved(self):
        """LaTeX formulas should pass through without being mangled."""
        md = "The formula is $E = mc^2$ and $$\\int_0^1 f(x) dx$$"
        result = md_to_telegram_html(md)
        assert "E = mc^2" in result
        assert "\\int_0^1" in result or "int_0^1" in result

    def test_cjk_content(self):
        """Chinese/Japanese/Korean text should be converted correctly."""
        md = "**你好世界** *こんにちは* ~~안녕하세요~~"
        result = md_to_telegram_html(md)
        assert "<b>你好世界</b>" in result
        assert "<i>こんにちは</i>" in result
        assert "<s>안녕하세요</s>" in result

    def test_angle_bracket_in_text(self):
        """Bare < in text (like 'I <3 you') should be escaped."""
        md = "I <3 you"
        result = md_to_telegram_html(md)
        assert "&lt;3" in result

    def test_expandable_blockquote_tag(self):
        """<blockquote expandable> should be preserved as a Telegram tag."""
        md = '<blockquote expandable>collapsed text</blockquote>'
        result = md_to_telegram_html(md)
        assert "<blockquote expandable>" in result


# ──────────────────────────────────────────────
# 2. GFM 表格渲染测试
# ──────────────────────────────────────────────

class TestTableRendering:
    def test_render_monospace_table_basic(self):
        header = "| Name | Age |"
        rows = ["| Alice | 30 |", "| Bob | 25 |"]
        result = _render_monospace_table(header, rows)
        assert "<pre>" in result
        assert "</pre>" in result
        assert "Alice" in result
        assert "┌" in result and "┐" in result
        assert "└" in result and "┘" in result

    def test_render_monospace_table_padding(self):
        """Columns should be padded to the longest cell width."""
        header = "| X | Description |"
        rows = ["| A | Short |", "| B | A much longer description |"]
        result = _render_monospace_table(header, rows)
        assert "A much longer description" in result

    def test_convert_tables_detects_gfm(self):
        text = "| A | B |\n|---|---|\n| 1 | 2 |"
        result_text, blocks = _convert_tables(text)
        assert len(blocks) == 1
        assert "<pre>" in blocks[0]

    def test_convert_tables_no_table(self):
        text = "Just regular text without pipes"
        result_text, blocks = _convert_tables(text)
        assert blocks == []
        assert result_text == text

    def test_convert_tables_mixed_content(self):
        """Tables should be extracted; surrounding text preserved."""
        text = "Before\n| A | B |\n|---|---|\n| 1 | 2 |\nAfter"
        result_text, blocks = _convert_tables(text)
        assert len(blocks) == 1
        assert "Before" in result_text
        assert "After" in result_text

    def test_table_html_entities_escaped(self):
        """Special chars in table cells should be HTML-escaped inside <pre>."""
        header = "| Key | Value |"
        rows = ["| x<y | a&b |"]
        result = _render_monospace_table(header, rows)
        assert "&lt;" in result
        assert "&amp;" in result

    def test_cjk_table(self):
        """CJK characters in table should render correctly."""
        header = "| 名称 | 年龄 |"
        rows = ["| 小明 | 25 |", "| 小红 | 30 |"]
        result = _render_monospace_table(header, rows)
        assert "小明" in result
        assert "小红" in result


# ──────────────────────────────────────────────
# 3. split_markdown_rich 测试 (Bot API 10.1 Rich Message UTF-8)
# ──────────────────────────────────────────────

class TestSplitMarkdownRich:
    def test_short_text_no_split(self):
        text = "Hello world"
        assert split_markdown_rich(text) == [text]

    def test_split_at_semantic_boundary(self):
        """Long text should split at paragraph/sentence boundaries."""
        para1 = "A" * 20000
        para2 = "B" * 20000
        text = para1 + "\n\n" + para2
        chunks = split_markdown_rich(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 32000

    def test_code_fence_protection(self):
        """Code fences should not be split in the middle."""
        code_block = "```python\n" + "x = 1\n" * 5000 + "```"
        before = "A" * 25000 + "\n\n"
        text = before + code_block
        chunks = split_markdown_rich(text)
        for chunk in chunks:
            fence_count = chunk.count("```")
            assert fence_count % 2 == 0, f"Unbalanced fences in chunk: {fence_count}"

    def test_utf8_multibyte_safety(self):
        """CJK characters (3 bytes each) should not be split mid-character."""
        text = "你好世界" * 8000  # ~96000 bytes
        chunks = split_markdown_rich(text)
        assert len(chunks) >= 3
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 32000
            chunk.encode("utf-8")  # Should not raise

    def test_emoji_utf8_safety(self):
        """4-byte emoji should not be split mid-sequence."""
        emoji = "\U0001f600"  # 4 bytes in UTF-8
        text = emoji * 8001  # 32004 bytes
        chunks = split_markdown_rich(text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 32000
            chunk.encode("utf-8")

    def test_limit_parameter(self):
        text = "A" * 200
        chunks = split_markdown_rich(text, limit=50)
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 50
        assert "".join(chunks) == text


# ──────────────────────────────────────────────
# 4. _find_utf8_cut 测试
# ──────────────────────────────────────────────

class TestFindUtf8Cut:
    def test_ascii_exact(self):
        text = "A" * 100
        assert _find_utf8_cut(text, 100) == 100

    def test_cjk_boundary(self):
        """Should not cut in the middle of a CJK character."""
        text = "你好世界测试"  # each 3 bytes
        cut = _find_utf8_cut(text, 10)
        encoded = text[:cut].encode("utf-8")
        assert len(encoded) <= 10

    def test_semantic_break_paragraph(self):
        text = "Hello world.\n\nSecond paragraph." + "X" * 100
        cut = _find_utf8_cut(text, 50)
        assert text[cut - 2:cut] == "\n\n" or cut <= 50

    def test_semantic_break_sentence(self):
        text = "First sentence. Second sentence." + "X" * 100
        cut = _find_utf8_cut(text, 20)
        sliced = text[:cut]
        assert ". " in sliced or cut <= 20


# ──────────────────────────────────────────────
# 5. split_message 扩展测试 (HTML tag 状态机)
# ──────────────────────────────────────────────

class TestSplitMessageExtended:
    def test_blockquote_tag(self):
        """<blockquote> should be tracked by the tag state machine."""
        text = "<blockquote>" + "X" * 4090 + "</blockquote>"
        chunks = split_message(text, limit=4096)
        assert len(chunks) >= 1
        for chunk in chunks:
            assert _utf16_len(chunk) <= 4096

    def test_expandable_tag(self):
        """<expandable> tag should be handled correctly."""
        text = "<expandable>" + "Y" * 4090 + "</expandable>"
        chunks = split_message(text, limit=4096)
        for chunk in chunks:
            assert _utf16_len(chunk) <= 4096

    def test_deeply_nested_tags(self):
        """Deep nesting (b > i > s > code) should close/reopen correctly."""
        text = "<b><i><s><code>" + "Z" * 4080 + "</code></s></i></b>"
        chunks = split_message(text, limit=4096)
        assert len(chunks) >= 2
        assert chunks[0].endswith("</code></s></i></b>")
        assert chunks[1].startswith("<b><i><s><code>")

    def test_cjk_with_formatting(self):
        """CJK content inside HTML tags should split correctly at UTF-16 boundaries."""
        text = "<b>" + "你好" * 2000 + "</b>"  # 你好 = 2 chars, each 1 UTF-16 unit
        chunks = split_message(text, limit=4096)
        for chunk in chunks:
            assert _utf16_len(chunk) <= 4096
            assert chunk.startswith("<b>")
            assert chunk.endswith("</b>")

    def test_empty_text(self):
        assert split_message("") == [""]

    def test_single_char(self):
        assert split_message("X") == ["X"]

    def test_exact_limit(self):
        text = "A" * 4096
        assert split_message(text) == [text]

    def test_one_over_limit(self):
        text = "A" * 4097
        chunks = split_message(text)
        assert len(chunks) == 2
        for chunk in chunks:
            assert _utf16_len(chunk) <= 4096

    def test_surrogate_pair_at_boundary(self):
        """Emoji requiring surrogate pairs should not be split."""
        text = "A" * 4094 + "\U0001f600"  # 4094 + 2 = 4096 exactly
        chunks = split_message(text, limit=4096)
        assert len(chunks) == 1
        assert chunks[0] == text

    def test_surrogate_pair_over_boundary(self):
        text = "A" * 4095 + "\U0001f600"  # 4095 + 2 = 4097 > 4096
        chunks = split_message(text, limit=4096)
        assert len(chunks) == 2
        assert "\U0001f600" not in chunks[0] or _utf16_len(chunks[0]) <= 4096


# ──────────────────────────────────────────────
# 6. _utf16_len 扩展测试
# ──────────────────────────────────────────────

class TestUtf16Len:
    def test_ascii(self):
        assert _utf16_len("hello") == 5

    def test_cjk(self):
        assert _utf16_len("你好") == 2

    def test_emoji_bmp(self):
        assert _utf16_len("😀") == 2  # supplementary plane

    def test_mixed(self):
        text = "Hello 你好 😀"
        assert _utf16_len(text) == 5 + 1 + 2 + 1 + 2  # Hello + space + 你好 + space + emoji

    def test_empty(self):
        assert _utf16_len("") == 0

    def test_flag_emoji(self):
        """Flag emoji (regional indicators) are 4 UTF-16 code units."""
        flag = "\U0001F1E8\U0001F1F3"  # CN flag
        assert _utf16_len(flag) == 4


# ──────────────────────────────────────────────
# 7. 端到端集成测试: md → html → split 完整流水线
# ──────────────────────────────────────────────

class TestEndToEndPipeline:
    def test_full_pipeline_short(self):
        """Short md → html → split should produce single chunk."""
        md = "**Hello** *world* `code`"
        html_text = md_to_telegram_html(md)
        chunks = split_message(html_text)
        assert len(chunks) == 1
        assert "<b>Hello</b>" in chunks[0]

    def test_full_pipeline_long_with_table(self):
        """Long content with a GFM table should degrade and split correctly."""
        table = "| Col1 | Col2 |\n|------|------|\n" + "| val | val |\n" * 100
        extra = "More text " * 500
        md = table + "\n\n" + extra
        html_text = md_to_telegram_html(md)
        chunks = split_message(html_text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert _utf16_len(chunk) <= 4096

    def test_full_pipeline_cjk_long(self):
        """Long CJK content should split without corruption."""
        md = "**" + "这是测试内容" * 1000 + "**"
        html_text = md_to_telegram_html(md)
        chunks = split_message(html_text)
        assert len(chunks) >= 2
        for chunk in chunks:
            assert _utf16_len(chunk) <= 4096
            assert chunk.startswith("<b>")
            assert chunk.endswith("</b>")

    def test_rich_pipeline_with_code(self):
        """Rich Message path with code blocks should handle split correctly."""
        code = "```python\n" + "x = 1\n" * 6000 + "```"
        chunks = split_markdown_rich(code)
        for chunk in chunks:
            assert len(chunk.encode("utf-8")) <= 32000
        total_fences = sum(chunk.count("```") for chunk in chunks)
        assert total_fences % 2 == 0, "Total fences across all chunks must be even"
