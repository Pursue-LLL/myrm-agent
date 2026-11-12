"""Tests for PptxParser on groups, charts and pictures.

These shapes carry slide content that a flat walk over `slide.shapes` silently drops:
text and data inside (nested) groups, chart series values and picture alt text.
"""

from __future__ import annotations

import io
import json
import logging
from pathlib import Path

import pytest
from PIL import Image
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.enum.chart import XL_CHART_TYPE
from pptx.presentation import Presentation as PptxPresentation
from pptx.shapes.shapetree import SlideShapes
from pptx.util import Inches

from myrm_agent_harness.toolkits.file_parsers import PptxParser

_BLANK_LAYOUT = 6
_PICTURE_WITH_CAPTION_LAYOUT = 8
_PARSER_LOGGER = "myrm_agent_harness.toolkits.file_parsers.pptx"


def _png() -> io.BytesIO:
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), "red").save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def _set_alt_text(picture_element: object, alt_text: str) -> None:
    picture_element.nvPicPr.cNvPr.set("descr", alt_text)  # type: ignore[attr-defined]


def _save(prs: PptxPresentation, tmp_path: Path) -> str:
    path = tmp_path / "deck.pptx"
    prs.save(str(path))
    return str(path)


def _blank_slide() -> tuple[PptxPresentation, SlideShapes]:
    prs = Presentation()
    return prs, prs.slides.add_slide(prs.slide_layouts[_BLANK_LAYOUT]).shapes


def _quarterly_chart_data() -> CategoryChartData:
    data = CategoryChartData()
    data.categories = ["Q1", "Q2"]
    data.add_series("Revenue", (240, 310.5))
    data.add_series("Cost", (100, None))
    return data


class TestGroupRecursion:
    @pytest.mark.asyncio
    async def test_grouped_text_is_extracted_in_document_order(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        shapes.add_textbox(Inches(1), Inches(0.5), Inches(2), Inches(0.5)).text_frame.text = "BEFORE"
        group = shapes.add_group_shape()
        group.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5)).text_frame.text = "GROUPED-API-GATEWAY"
        nested = group.shapes.add_group_shape()
        nested.shapes.add_textbox(Inches(1), Inches(2), Inches(2), Inches(0.5)).text_frame.text = "NESTED-GROUP-WORKER"
        shapes.add_textbox(Inches(1), Inches(3), Inches(2), Inches(0.5)).text_frame.text = "AFTER"

        result = await PptxParser().parse(_save(prs, tmp_path))

        positions = [result.index(label) for label in ("BEFORE", "GROUPED-API-GATEWAY", "NESTED-GROUP-WORKER", "AFTER")]
        assert positions == sorted(positions)

    @pytest.mark.asyncio
    async def test_slide_with_only_a_group_is_not_empty(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        group = shapes.add_group_shape()
        group.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5)).text_frame.text = "ONLY-IN-GROUP"

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert result != "(Empty presentation)"
        assert "ONLY-IN-GROUP" in result

    @pytest.mark.asyncio
    async def test_chart_inside_a_group_is_extracted(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        group = shapes.add_group_shape()
        group.shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(4), Inches(3), _quarterly_chart_data()
        )

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert "| Q1 | 240 | 100 |" in result


class TestChart:
    @pytest.mark.asyncio
    async def test_category_chart_renders_title_and_series_table(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        graphic_frame = shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(4), Inches(3), _quarterly_chart_data()
        )
        graphic_frame.chart.has_title = True
        graphic_frame.chart.chart_title.text_frame.text = "Quarterly results"

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert "**Chart: Quarterly results**" in result
        assert "|  | Revenue | Cost |" in result
        assert "| --- | --- | --- |" in result
        assert "| Q1 | 240 | 100 |" in result
        # A fractional value keeps its decimals and a missing point is an empty cell.
        assert "| Q2 | 310.5 |  |" in result

    @pytest.mark.asyncio
    async def test_pipe_in_series_name_is_escaped(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        data = CategoryChartData()
        data.categories = ["Q1"]
        data.add_series("A|B", (1,))
        shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(4), Inches(3), data)

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert "|  | A\\|B |" in result

    @pytest.mark.asyncio
    async def test_chart_without_categories_lists_each_series(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        data = XyChartData()
        series = data.add_series("Latency")
        series.add_data_point(1, 20)
        series.add_data_point(2, 35.5)
        shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, Inches(1), Inches(1), Inches(4), Inches(3), data)

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert "- Latency: 20, 35.5" in result

    @pytest.mark.asyncio
    async def test_unreadable_chart_value_skips_only_that_chart(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        prs, shapes = _blank_slide()
        shapes.add_textbox(Inches(1), Inches(0.5), Inches(2), Inches(0.5)).text_frame.text = "KEEP-THIS-TEXT"
        graphic_frame = shapes.add_chart(
            XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(1), Inches(1), Inches(4), Inches(3), _quarterly_chart_data()
        )
        graphic_frame.chart._chartSpace.xpath(".//c:val//c:v")[0].text = "#N/A"

        with caplog.at_level(logging.WARNING, logger=_PARSER_LOGGER):
            result = await PptxParser().parse(_save(prs, tmp_path))

        assert "KEEP-THIS-TEXT" in result
        assert "Revenue" not in result
        assert "Skipping unreadable chart" in caplog.text


class TestPictureAltText:
    @pytest.mark.asyncio
    async def test_free_picture_and_grouped_picture_alt_text(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        free = shapes.add_picture(_png(), Inches(1), Inches(1), Inches(1), Inches(1))
        _set_alt_text(free.element, "ALT-free-picture")
        group = shapes.add_group_shape()
        grouped = group.shapes.add_picture(_png(), Inches(3), Inches(1), Inches(1), Inches(1))
        _set_alt_text(grouped.element, "ALT-grouped-picture")
        # python-pptx fills `descr` with the file name on insert; a picture without alt text has it empty.
        unlabeled = shapes.add_picture(_png(), Inches(5), Inches(1), Inches(1), Inches(1))
        _set_alt_text(unlabeled.element, "")

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert "[Image: ALT-free-picture]" in result
        assert "[Image: ALT-grouped-picture]" in result
        assert result.count("[Image:") == 2

    @pytest.mark.asyncio
    async def test_picture_placeholder_alt_text(self, tmp_path: Path) -> None:
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[_PICTURE_WITH_CAPTION_LAYOUT])
        placeholder_picture = slide.placeholders[1].insert_picture(_png())  # type: ignore[attr-defined]
        _set_alt_text(placeholder_picture.element, "ALT-placeholder-picture")

        result = await PptxParser().parse(_save(prs, tmp_path))

        assert "[Image: ALT-placeholder-picture]" in result


class TestStructureGroups:
    @pytest.mark.asyncio
    async def test_group_lists_children_recursively(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        group = shapes.add_group_shape()
        child = group.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5))
        child.text_frame.text = "GROUPED-API-GATEWAY"
        nested = group.shapes.add_group_shape()
        nested_child = nested.shapes.add_textbox(Inches(1), Inches(2), Inches(2), Inches(0.5))
        nested_child.text_frame.text = "NESTED-GROUP-WORKER"

        data = json.loads(await PptxParser(output_format="structure").parse(_save(prs, tmp_path)))

        group_info = data["slides"][0]["shapes"][0]
        assert group_info["type"] == "group"
        children = {c["shape_id"]: c for c in group_info["children"]}
        assert children[child.shape_id]["text_preview"] == "GROUPED-API-GATEWAY"
        nested_info = next(c for c in group_info["children"] if c["type"] == "group")
        assert nested_info["children"][0]["shape_id"] == nested_child.shape_id
        assert nested_info["children"][0]["text_preview"] == "NESTED-GROUP-WORKER"

    @pytest.mark.asyncio
    async def test_shape_count_counts_top_level_shapes_only(self, tmp_path: Path) -> None:
        prs, shapes = _blank_slide()
        shapes.add_textbox(Inches(1), Inches(0.5), Inches(2), Inches(0.5))
        group = shapes.add_group_shape()
        group.shapes.add_textbox(Inches(1), Inches(1), Inches(2), Inches(0.5))
        group.shapes.add_textbox(Inches(1), Inches(2), Inches(2), Inches(0.5))

        data = json.loads(await PptxParser(output_format="structure").parse(_save(prs, tmp_path)))

        slide = data["slides"][0]
        assert slide["shape_count"] == 2
        assert len(slide["shapes"]) == 2

    @pytest.mark.asyncio
    async def test_picture_placeholder_is_a_picture_with_alt_text(self, tmp_path: Path) -> None:
        prs = Presentation()
        slide = prs.slides.add_slide(prs.slide_layouts[_PICTURE_WITH_CAPTION_LAYOUT])
        placeholder_picture = slide.placeholders[1].insert_picture(_png())  # type: ignore[attr-defined]
        _set_alt_text(placeholder_picture.element, "ALT-placeholder-picture")

        data = json.loads(await PptxParser(output_format="structure").parse(_save(prs, tmp_path)))

        picture = next(s for s in data["slides"][0]["shapes"] if s["type"] == "picture")
        assert picture["has_image"] is True
        assert picture["alt_text"] == "ALT-placeholder-picture"
        assert picture["placeholder_idx"] == 1
