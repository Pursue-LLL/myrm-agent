"""PowerPoint document parser

Uses python-pptx for parsing PPTX files with support for:
- Slide text extraction (titles, body, text boxes), including text inside nested groups
- Table and chart extraction with Markdown output (charts: title, categories, series values)
- Picture alt text
- Speaker notes extraction
- Structure mode: JSON metadata with shape IDs, positions, types for incremental edits;
  group shapes list their children

[INPUT]
- (none)

[OUTPUT]
- PptxParser: PowerPoint document parser using python-pptx

[POS]
PowerPoint document parser
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.toolkits.file_parsers.base import FileParser

if TYPE_CHECKING:
    from pptx.chart.chart import Chart
    from pptx.presentation import Presentation as PptxPresentation
    from pptx.shapes.base import BaseShape
    from pptx.shapes.picture import Picture
    from pptx.slide import Slide
    from pptx.table import Table

logger = logging.getLogger(__name__)

PptxOutputFormat = Literal["markdown", "structure"]

_EMU_PER_CM = 360_000
_PREVIEW_CHARS = 200


def _emu_to_cm(emu: int | None) -> float | None:
    """Convert EMU (English Metric Units) to centimeters."""
    return round(emu / _EMU_PER_CM, 2) if emu is not None else None


def _md_cell(text: str) -> str:
    """Escape text for use inside a Markdown table cell."""
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _render_markdown_table(rows: list[list[str]]) -> str:
    """Render rows as a Markdown table: the first row is the header, short rows are padded."""
    if not rows:
        return ""

    headers = rows[0]
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows[1:]:
        padded = row + [""] * (len(headers) - len(row))
        lines.append("| " + " | ".join(padded) + " |")
    return "\n".join(lines)


def _extract_table(table: Table) -> str:
    """Extract a PowerPoint table as Markdown."""
    return _render_markdown_table([[_md_cell(cell.text) for cell in row.cells] for row in table.rows])


def _format_chart_value(value: float | None) -> str:
    """Render a chart data point; a missing point is an empty cell, whole numbers drop the `.0`."""
    if value is None:
        return ""
    return str(int(value)) if value.is_integer() else str(value)


def _extract_chart(chart: Chart) -> str:
    """Render a chart's title and series values as Markdown.

    A category chart becomes one table per plot (rows are categories, columns are series). A
    chart without categories (XY, bubble) lists each series as one line of y values; its x
    values are not read.
    """
    parts: list[str] = []
    if chart.has_title and chart.chart_title.has_text_frame:
        title = chart.chart_title.text_frame.text.strip()
        if title:
            parts.append(f"**Chart: {title}**")

    for plot in chart.plots:
        series = list(plot.series)
        if not series:
            continue

        columns = [[_format_chart_value(value) for value in s.values] for s in series]
        labels = [" / ".join(path) for path in plot.categories.flattened_labels]
        if not labels:
            parts.extend(f"- {s.name}: {', '.join(column)}" for s, column in zip(series, columns, strict=True))
            continue

        rows = [["", *(_md_cell(s.name) for s in series)]]
        for index in range(max(len(labels), *(len(column) for column in columns))):
            label = _md_cell(labels[index]) if index < len(labels) else ""
            rows.append([label, *(column[index] if index < len(column) else "" for column in columns)])
        parts.append(_render_markdown_table(rows))

    return "\n\n".join(parts)


def _picture_alt_text(picture: Picture) -> str:
    """Return the alt text the author gave a picture (`descr`), or an empty string."""
    descr = picture.element.xpath("./p:nvPicPr/p:cNvPr/@descr")
    return str(descr[0]).strip() if descr else ""


def _iter_shapes(shapes: Iterable[BaseShape]) -> Iterator[BaseShape]:
    """Yield shapes in document order, descending into (nested) group shapes."""
    from pptx.shapes.group import GroupShape

    for shape in shapes:
        if isinstance(shape, GroupShape):
            yield from _iter_shapes(shape.shapes)
        else:
            yield shape


def _collect_shape_markdown(shape: BaseShape, text_parts: list[str], data_parts: list[str]) -> None:
    """Add one shape's Markdown: text and picture alt text to `text_parts`, tables and charts to `data_parts`."""
    from pptx.shapes.autoshape import Shape
    from pptx.shapes.graphfrm import GraphicFrame
    from pptx.shapes.picture import Picture

    if isinstance(shape, GraphicFrame) and shape.has_table:
        data_parts.append(_extract_table(shape.table))
    elif isinstance(shape, GraphicFrame) and shape.has_chart:
        try:
            chart_markdown = _extract_chart(shape.chart)
        except ValueError as exc:
            # python-pptx converts cached chart values with float(); one malformed value must not fail the deck.
            logger.warning("Skipping unreadable chart %r: %s", shape.name, exc)
            return
        if chart_markdown:
            data_parts.append(chart_markdown)
    elif isinstance(shape, Picture):
        alt_text = _picture_alt_text(shape)
        if alt_text:
            text_parts.append(f"[Image: {alt_text}]")
    elif isinstance(shape, Shape):
        for paragraph in shape.text_frame.paragraphs:
            text = paragraph.text.strip()
            if text:
                text_parts.append(text)


def _classify_shape(shape: BaseShape) -> str:
    """Classify a shape into a human-readable type string."""
    from pptx.shapes.autoshape import Shape
    from pptx.shapes.graphfrm import GraphicFrame
    from pptx.shapes.group import GroupShape
    from pptx.shapes.picture import Picture

    if isinstance(shape, GroupShape):
        return "group"
    if isinstance(shape, GraphicFrame):
        if shape.has_table:
            return "table"
        if shape.has_chart:
            return "chart"
    if isinstance(shape, Picture):
        return "picture"
    if isinstance(shape, Shape):
        try:
            idx = shape.placeholder_format.idx
        except ValueError:
            return "text_box"
        if idx == 0:
            return "title"
        if idx == 1:
            return "body"
        return "placeholder"
    return "other"


def _describe_shape(shape: BaseShape) -> dict[str, object]:
    """Describe one shape for structure mode; a group lists its children under `children`.

    A child's `position_cm` is expressed in its group's own coordinate space, not slide space.
    """
    from pptx.shapes.autoshape import Shape
    from pptx.shapes.graphfrm import GraphicFrame
    from pptx.shapes.group import GroupShape
    from pptx.shapes.picture import Picture

    info: dict[str, object] = {
        "shape_id": shape.shape_id,
        "name": shape.name,
        "type": _classify_shape(shape),
        "position_cm": {
            "left": _emu_to_cm(shape.left),
            "top": _emu_to_cm(shape.top),
            "width": _emu_to_cm(shape.width),
            "height": _emu_to_cm(shape.height),
        },
    }

    # Raises ValueError for shapes that are not placeholders.
    with contextlib.suppress(ValueError):
        info["placeholder_idx"] = shape.placeholder_format.idx

    if isinstance(shape, Shape):
        info["text_preview"] = shape.text_frame.text.strip()[:_PREVIEW_CHARS]
    if isinstance(shape, GraphicFrame) and shape.has_table:
        info["table_size"] = {"rows": len(shape.table.rows), "cols": len(shape.table.columns)}
    if isinstance(shape, Picture):
        info["has_image"] = True
        alt_text = _picture_alt_text(shape)
        if alt_text:
            info["alt_text"] = alt_text[:_PREVIEW_CHARS]
    if isinstance(shape, GroupShape):
        info["children"] = [_describe_shape(child) for child in shape.shapes]

    return info


def _notes_text(slide: Slide) -> str:
    """Return the slide's speaker notes, or an empty string."""
    if not slide.has_notes_slide:
        return ""
    notes_frame = slide.notes_slide.notes_text_frame
    return notes_frame.text.strip() if notes_frame is not None else ""


class PptxParser(FileParser):
    """PowerPoint document parser using python-pptx

    Extracts slide text (including text inside groups), tables, charts, picture alt text,
    and speaker notes into Markdown format. Each slide becomes a section with heading and content.
    Structure mode outputs JSON metadata with shape IDs, positions, and types
    for enabling precise incremental edits.
    """

    def __init__(self, output_format: PptxOutputFormat = "markdown"):
        self._output_format: PptxOutputFormat = output_format

    async def parse(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        content = await asyncio.to_thread(self._parse_sync, file_path)

        logger.info("PowerPoint parsed: %s, format=%s, length: %d chars", path.name, self._output_format, len(content))
        return content

    def _parse_sync(self, file_path: str) -> str:
        try:
            from pptx import Presentation
        except ImportError as e:
            raise ImportError("python-pptx is not installed. Run: uv add python-pptx") from e

        prs = Presentation(file_path)

        if self._output_format == "structure":
            return self._build_structure(prs)

        return self._build_markdown(prs)

    def _build_markdown(self, prs: PptxPresentation) -> str:
        """Build Markdown content from presentation."""
        slides_output: list[str] = []

        for slide_idx, slide in enumerate(prs.slides, start=1):
            slide_parts: list[str] = [f"## Slide {slide_idx}"]

            text_parts: list[str] = []
            data_parts: list[str] = []  # tables and charts follow the slide text

            for shape in _iter_shapes(slide.shapes):
                _collect_shape_markdown(shape, text_parts, data_parts)

            if text_parts:
                slide_parts.append("\n".join(text_parts))
            slide_parts.extend(data_parts)

            notes_text = _notes_text(slide)
            if notes_text:
                slide_parts.append(f"\n> **Notes:** {notes_text}")

            if len(slide_parts) > 1:
                slides_output.append("\n\n".join(slide_parts))

        return "\n\n---\n\n".join(slides_output) if slides_output else "(Empty presentation)"

    def _build_structure(self, prs: PptxPresentation) -> str:
        """Return JSON structural metadata for the presentation."""
        slides_meta: list[dict[str, object]] = []

        for slide_idx, slide in enumerate(prs.slides, start=1):
            shapes_meta = [_describe_shape(shape) for shape in slide.shapes]

            slide_meta: dict[str, object] = {
                "slide_number": slide_idx,
                "layout": slide.slide_layout.name if slide.slide_layout else None,
                "shape_count": len(shapes_meta),
                "shapes": shapes_meta,
            }
            notes_text = _notes_text(slide)
            if notes_text:
                slide_meta["notes_preview"] = notes_text[:_PREVIEW_CHARS]

            slides_meta.append(slide_meta)

        result: dict[str, object] = {
            "slide_count": len(slides_meta),
            "slide_size_cm": {"width": _emu_to_cm(prs.slide_width), "height": _emu_to_cm(prs.slide_height)},
            "slides": slides_meta,
        }
        return json.dumps(result, ensure_ascii=False, separators=(",", ":"))

    @property
    def supported_extensions(self) -> list[str]:
        return [".pptx"]
