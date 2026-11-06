"""Table conversion of the HTML-to-Markdown converter: layout, nested tables and unclosed rows."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.web_fetch.processing.html_to_markdown import CustomHTML2Text
from myrm_agent_harness.toolkits.web_fetch.processing.markdown_table import render_markdown_table


def _convert(html: str) -> str:
    return CustomHTML2Text().handle(html)


class TestRenderMarkdownTable:
    def test_first_row_is_the_header_when_the_table_has_one(self) -> None:
        rendered = render_markdown_table([["a", "b"], ["1", "2"]], has_header=True)

        assert rendered == "\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\n"

    def test_blank_header_is_added_when_the_table_has_none(self) -> None:
        rendered = render_markdown_table([["a", "b"], ["1", "2"]], has_header=False)

        assert rendered == "\n\n|  |  |\n| --- | --- |\n| a | b |\n| 1 | 2 |\n\n"

    def test_header_and_delimiter_span_the_widest_row_without_touching_the_input(self) -> None:
        rows = [["a"], ["1", "2", "3"]]

        rendered = render_markdown_table(rows, has_header=True)

        assert rendered == "\n\n| a |  |  |\n| --- | --- | --- |\n| 1 | 2 | 3 |\n\n"
        assert rows == [["a"], ["1", "2", "3"]]

    def test_a_short_body_row_keeps_the_cells_it_has(self) -> None:
        rendered = render_markdown_table([["a", "b", "c"], ["1"], ["x", "y"]], has_header=True)

        assert rendered == "\n\n| a | b | c |\n| --- | --- | --- |\n| 1 |\n| x | y |\n\n"

    def test_the_output_grows_with_the_cells_not_with_rows_times_the_widest_row(self) -> None:
        wide, short_rows = 2000, 2000
        rows = [["h"] * wide, *([["x"]] * short_rows)]

        rendered = render_markdown_table(rows, has_header=True)

        assert len(rendered) < 16 * (wide + short_rows)


class TestFlatTables:
    @pytest.mark.parametrize(
        ("html", "expected"),
        [
            pytest.param(
                "<table><thead><tr><th>Name</th><th>Qty</th></tr></thead>"
                "<tbody><tr><td>apple</td><td>3</td></tr></tbody></table>",
                "| Name | Qty |\n| --- | --- |\n| apple | 3 |\n",
                id="thead-is-the-header",
            ),
            pytest.param(
                "<table><tr><td>apple</td><td>3</td></tr><tr><td>pear</td><td>5</td></tr></table>",
                "|  |  |\n| --- | --- |\n| apple | 3 |\n| pear | 5 |\n",
                id="blank-header-without-thead",
            ),
            pytest.param(
                "<table><tr><td>a|b</td><td><p>x</p><p>y</p></td></tr></table>",
                "|  |  |\n| --- | --- |\n| a\\|b | x    y |\n",
                id="pipes-escaped-and-newlines-folded",
            ),
            pytest.param(
                "<table><tr><td>a</td></tr><tr><td>1</td><td>2</td><td>3</td></tr></table>",
                "|  |  |  |\n| --- | --- | --- |\n| a |\n| 1 | 2 | 3 |\n",
                id="short-body-rows-keep-their-cells",
            ),
            pytest.param("<table><td>a</td><td>b</td></table>", "ab\n", id="table-without-rows-is-plain-text"),
        ],
    )
    def test_layout(self, html: str, expected: str) -> None:
        assert _convert(html) == expected


class TestNestedTables:
    def test_nested_rows_are_listed_once_after_the_row_that_holds_them(self) -> None:
        html = (
            "<table><tr><td>outer</td><td><table><tr><td>in-1</td></tr><tr><td>in-2</td></tr></table></td></tr></table>"
        )

        assert _convert(html) == "|  |  |\n| --- | --- |\n| outer |  |\n| in-1 |\n| in-2 |\n"

    def test_text_around_a_nested_table_stays_in_its_cell(self) -> None:
        html = "<table><tr><td>before <table><tr><td>in</td></tr></table> after</td><td>side</td></tr></table>"

        assert _convert(html) == "|  |  |\n| --- | --- |\n| before  after | side |\n| in |\n"

    def test_nested_table_without_rows_is_converted_in_place(self) -> None:
        html = "<table><tr><td>pre <table><td>x</td></table> post</td></tr></table>"

        assert _convert(html) == "|  |\n| --- |\n| pre x post |\n"

    @pytest.mark.parametrize("depth", [2, 5, 14])
    def test_every_level_of_a_nesting_chain_is_listed_exactly_once(self, depth: int) -> None:
        html = "<table><tr><td>cell" * depth + "x" + "</td></tr></table>" * depth

        converted = _convert(html)

        assert converted.count("cell") == depth
        assert len(converted) <= len(html)


class TestRowsOfUnequalWidth:
    @pytest.mark.timeout(30)
    def test_one_wide_row_and_many_short_rows_keep_the_output_shorter_than_the_input(self) -> None:
        wide, short_rows = 1500, 1500
        html = "<table><tr>" + "<td>h</td>" * wide + "</tr>" + "<tr><td>x</td></tr>" * short_rows + "</table>"

        converted = _convert(html)

        assert converted.count("| x |") == short_rows
        assert len(converted) <= len(html)


class TestUnclosedRows:
    @pytest.mark.timeout(30)
    def test_rows_that_are_never_closed_keep_the_output_proportional_to_the_input(self) -> None:
        rows = 300
        html = "<table>" + "".join(f"<tr><td>row{i}a<td>row{i}b" for i in range(rows)) + "</table>"

        converted = _convert(html)

        assert converted.count("row0a") == 1
        assert converted.count(f"row{rows - 1}b") == 1
        assert len(converted) <= len(html)


class TestConverterReuse:
    def test_converter_still_renders_tables_after_a_cell_failed(self) -> None:
        converter = CustomHTML2Text()
        with pytest.raises(ValueError, match="invalid literal"):
            converter.handle('<table><tr><td><ol start="abc"><li>x</li></ol></td></tr></table>')

        assert converter.handle("<table><tr><td>a</td></tr></table>") == "|  |\n| --- |\n| a |\n"
