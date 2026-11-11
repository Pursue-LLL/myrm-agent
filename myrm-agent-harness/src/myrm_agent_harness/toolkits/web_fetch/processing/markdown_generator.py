"""Markdown generator

Converts HTML to Markdown and, when a content filter is configured, also
produces the filtered ("fit") variant that keeps only the main content.

[INPUT]
- processing.html_to_markdown::CustomHTML2Text (POS: HTML-to-Markdown converter) [lazy]

[OUTPUT]
- MarkdownResult: raw / fit Markdown plus the filtered HTML
- ContentFilter: content filter protocol
- MarkdownGenerator: HTML → Markdown generator with an optional content filter

[POS]
Markdown generation stage of ContentPipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(slots=True)
class MarkdownResult:
    """Result of one HTML → Markdown conversion."""

    raw_markdown: str = ""
    fit_markdown: str = ""
    fit_html: str = ""


@runtime_checkable
class ContentFilter(Protocol):
    """Content filter protocol."""

    def filter_content(self, html: str) -> list[str]: ...


class MarkdownGenerator:
    """HTML → Markdown generator with an optional content filter."""

    def __init__(
        self,
        content_filter: ContentFilter | None = None,
        options: dict[str, object] | None = None,
    ):
        self.content_filter = content_filter
        self.options = options or {}

    def generate_markdown(
        self,
        input_html: str,
        base_url: str = "",
        html2text_options: dict[str, object] | None = None,
        content_filter: ContentFilter | None = None,
    ) -> MarkdownResult:
        from .html_to_markdown import CustomHTML2Text

        try:
            h = CustomHTML2Text(baseurl=base_url)
            default_options: dict[str, object] = {
                "body_width": 0,
                "ignore_emphasis": False,
                "ignore_links": False,
                "ignore_images": False,
                "protect_links": False,
                "single_line_break": False,
                "mark_code": False,
                "escape_snob": False,
                "skip_internal_links": True,
            }

            if html2text_options:
                default_options.update(html2text_options)
            elif self.options:
                default_options.update(self.options)

            h.update_params(**default_options)

            if not input_html:
                input_html = ""

            try:
                raw_markdown = h.handle(input_html)
            except Exception as e:
                raw_markdown = f"Error converting HTML to markdown: {e}"

            raw_markdown = raw_markdown.replace("    ```", "```")

            fit_markdown: str = ""
            filtered_html: str = ""
            active_filter = content_filter or self.content_filter
            if active_filter:
                try:
                    filtered_segments = active_filter.filter_content(input_html)
                    filtered_html = "\n".join(f"<div>{s}</div>" for s in filtered_segments)
                    fit_markdown = h.handle(filtered_html)
                except Exception as e:
                    fit_markdown = f"Error generating fit markdown: {e}"
                    filtered_html = ""

            return MarkdownResult(
                raw_markdown=raw_markdown or "",
                fit_markdown=fit_markdown or "",
                fit_html=filtered_html or "",
            )
        except Exception as e:
            return MarkdownResult(raw_markdown=f"Error in markdown generation: {e}")
