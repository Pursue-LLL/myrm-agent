"""ContentPipeline — Converts HTML into LLM-friendly Documents.

Unified content processing pipeline, decoupled from the Fetcher layer:
regardless of whether HTML comes from curl_cffi, Patchright, or Scrapling,
it passes through the same processing pipeline.

[INPUT]
web_fetch.processing.content_pruning::ContentPruningFilter (POS: Boilerplate / noise pruning)
web_fetch.processing.html_scan::extract_title (POS: Linear-time scans of raw HTML text)
web_fetch.fetchers.protocol::FetcherType, FetchResult (POS: Fetcher protocol types)
web_fetch.processing.markdown_generator::MarkdownGenerator (POS: HTML-to-Markdown conversion)
utils.text_cleaner::clean_text (POS: Generic text cleaning utility)

[OUTPUT]
ContentPipeline: Transforms raw FetchResult HTML into cleaned, Markdown-formatted Documents
(``process`` synchronously, ``aprocess`` on a dedicated conversion thread)

[POS]
Content processing pipeline. Sits between the fetcher layer and the consumer layer,
converting raw HTML into clean Markdown Documents with metadata.

"""

from __future__ import annotations

import asyncio
import atexit
import contextvars
import json
import logging
from concurrent.futures import ThreadPoolExecutor

from langchain_core.documents import Document

from myrm_agent_harness.utils.text_cleaner import clean_text

from ..fetchers.protocols import FetcherType, FetchResult
from .content_pruning import ContentPruningFilter
from .html_scan import extract_title
from .markdown_generator import MarkdownGenerator

logger = logging.getLogger(__name__)

_MIN_CONTENT_LENGTH = 50
_FIT_MARKDOWN_THRESHOLD = 100

# One worker on purpose: conversions stay serial (as they were on the event loop) and a conversion that keeps running
# after its awaiting task was cancelled is the only orphan there can be; futures still queued are dropped unstarted.
_CONVERSION_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="web-fetch-convert")
atexit.register(_CONVERSION_EXECUTOR.shutdown, wait=False, cancel_futures=True)


class ContentPipeline:
    """HTML → filter → Markdown → Document"""

    def __init__(self, *, use_raw_markdown: bool = False):
        self._use_raw_markdown = use_raw_markdown
        self._md_generator = self._create_markdown_generator()

    def _create_markdown_generator(self) -> MarkdownGenerator | None:
        if self._use_raw_markdown:
            return None
        return MarkdownGenerator(
            content_filter=ContentPruningFilter(
                threshold=0.48,
                metric_weights={
                    "text_density": 0.32,
                    "link_density": 0.25,
                    "tag_weight": 0.33,
                    "class_id_weight": 0.08,
                    "text_length": 0.02,
                },
            ),
        )

    def _extract_raw_markdown(self, html: str, base_url: str) -> str:
        from .html_to_markdown import CustomHTML2Text

        h = CustomHTML2Text(baseurl=base_url)
        h.update_params(body_width=0)
        return h.handle(html).strip()

    def _extract_with_generator(
        self, html: str, base_url: str, is_stealth: bool, max_chars: int = 0
    ) -> tuple[str, bool]:
        assert self._md_generator is not None
        result = self._md_generator.generate_markdown(
            input_html=html,
            base_url=base_url,
            content_filter=self._md_generator.content_filter,
            max_chars=max_chars,
        )

        fit = result.fit_markdown.strip()
        if is_stealth:
            if not fit or len(fit) < _FIT_MARKDOWN_THRESHOLD:
                logger.warning("fit_markdown too short for stealth page, falling back to raw_markdown")
                return clean_text(result.raw_markdown), result.was_truncated
            return clean_text(fit), result.was_truncated

        return (fit, result.was_truncated) if len(fit) > _FIT_MARKDOWN_THRESHOLD else ("", False)

    def _try_structured_data_bypass(self, fetch_result: FetchResult, max_chars: int = 0) -> Document | None:
        content_type = (
            fetch_result.headers.get("content-type") or fetch_result.headers.get("Content-Type") or ""
        ).lower()
        body_text = fetch_result.html.strip()

        # 1. JSON bypass
        if "application/json" in content_type or (body_text.startswith(("{", "[")) and body_text.endswith(("}", "]"))):
            try:
                parsed = json.loads(body_text)
                formatted_json = json.dumps(parsed, indent=2, ensure_ascii=False)
                was_truncated = False
                if max_chars > 0 and len(formatted_json) > max_chars:
                    formatted_json = formatted_json[:max_chars] + "\n\n[TRUNCATED]"
                    was_truncated = True
                content = f"```json\n{formatted_json}\n```"
                return Document(
                    page_content=content,
                    metadata={
                        "url": fetch_result.url,
                        "title": f"JSON Data ({fetch_result.url})",
                        "description": "Raw JSON response",
                        "was_truncated": was_truncated,
                    },
                )
            except (json.JSONDecodeError, ValueError):
                pass

        # 2. XML / RSS / Atom bypass
        if "application/xml" in content_type or "text/xml" in content_type:
            was_truncated = False
            content = body_text
            if max_chars > 0 and len(content) > max_chars:
                content = content[:max_chars] + "\n\n[TRUNCATED]"
                was_truncated = True
            wrapped = f"```xml\n{content}\n```"
            return Document(
                page_content=wrapped,
                metadata={
                    "url": fetch_result.url,
                    "title": f"XML Data ({fetch_result.url})",
                    "description": "Raw XML response",
                    "was_truncated": was_truncated,
                },
            )

        return None

    def process(self, fetch_result: FetchResult, max_chars: int = 0) -> Document | None:
        """Converts FetchResult HTML or structured data into a clean Document."""
        # Fast path: check for structured JSON / XML data bypass
        structured_doc = self._try_structured_data_bypass(fetch_result, max_chars)
        if structured_doc is not None:
            return structured_doc

        was_truncated = False
        if self._md_generator is None:
            content = self._extract_raw_markdown(fetch_result.html, fetch_result.url)
            if max_chars > 0 and len(content) > max_chars:
                content = content[:max_chars] + "\n\n[TRUNCATED]"
                was_truncated = True
        else:
            is_stealth = fetch_result.fetcher_type == FetcherType.STEALTH
            content, was_truncated = self._extract_with_generator(
                fetch_result.html, fetch_result.url, is_stealth, max_chars
            )

        if not content or len(content.strip()) < _MIN_CONTENT_LENGTH:
            return None

        title = (extract_title(fetch_result.html) or "").strip()
        metadata: dict[str, str | bool] = {
            "url": fetch_result.url,
            "title": title,
            "description": "",
            "was_truncated": was_truncated,
        }

        return Document(page_content=content, metadata=metadata)

    async def aprocess(self, fetch_result: FetchResult, max_chars: int = 0) -> Document | None:
        """Run :meth:`process` on the dedicated conversion thread.

        Conversion is CPU-bound Python. On the event loop it would freeze every other request (streams, parallel
        fetches) for as long as it runs, and the fetch timeout cannot interrupt it there.
        """
        context = contextvars.copy_context()

        def convert() -> Document | None:
            return context.run(self.process, fetch_result, max_chars)

        return await asyncio.get_running_loop().run_in_executor(_CONVERSION_EXECUTOR, convert)
