"""Content extraction — single responsibility.


[INPUT]
- patchright.async_api::Page (POS: Patchright page instance)
- diff::FastComparisonResult (POS: fast comparison result)
- diff::AccurateComparisonResult (POS: accurate comparison result)
- media_extractor::extract_page_media (POS: media half of content extraction, one script per frame)

[OUTPUT]
- Extractor: content extraction manager

[POS]
Content extraction manager. Responsibilities:
1. Text extraction (DOM→Markdown with SVG text/tspan support)
2. Screenshot capture (JPEG compression)
3. Screenshot comparison (fast dHash / accurate Canvas API)
4. PDF export
5. Visual content detection (Canvas/SVG significance check for vision fallback)
6. Media extraction (images/videos/audio direct URLs with intelligent filtering; the work lives in media_extractor)

Single responsibility: only handles content extraction logic; does not handle navigation, snapshot, interaction, etc.
"""

from __future__ import annotations

import base64
import logging
from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.toolkits.browser.diff import (
    AccurateComparisonResult,
    FastComparisonResult,
)
from myrm_agent_harness.toolkits.browser.diff.screenshot_comparator import (
    ScreenshotComparator,
)
from myrm_agent_harness.toolkits.browser.session.media_extractor import extract_page_media
from myrm_agent_harness.toolkits.browser.utils.selectors import PASSWORD_FIELD_SELECTOR

if TYPE_CHECKING:
    from patchright.async_api import Page, PdfMargins

logger = logging.getLogger(__name__)

_SCREENSHOT_QUALITY = 50
_SCREENSHOT_MAX_WIDTH = 1280
_SCREENSHOT_MAX_HEIGHT = 720

_PDF_HEADER_TEMPLATE = (
    '<div style="font-size:8px;width:100%;padding:0 12px;color:#666"><span class="title"></span></div>'
)
_PDF_FOOTER_TEMPLATE = (
    '<div style="font-size:8px;width:100%;padding:0 12px;color:#666;'
    'display:flex;justify-content:space-between">'
    '<span class="url" style="max-width:70%;overflow:hidden;'
    'text-overflow:ellipsis;white-space:nowrap"></span>'
    '<span><span class="date"></span> &mdash; '
    '<span class="pageNumber"></span>/<span class="totalPages"></span></span>'
    "</div>"
)
_PDF_MARGIN: PdfMargins = {"top": "20px", "bottom": "28px", "left": "0", "right": "0"}


class Extractor:
    """Content extraction manager — single responsibility.

    Capabilities:
    1. Text extraction (DOM→Markdown with SVG text/tspan support)
    2. Screenshot capture (JPEG compression)
    3. Screenshot comparison (fast dHash / accurate Canvas API)
    4. PDF export
    5. Visual content detection (Canvas/SVG significance check)
    6. Media extraction (images/videos/audio direct URLs with intelligent filtering)

    Does NOT handle: navigation, snapshot generation, element interaction.
    """

    def __init__(self, page: Page):
        """Initialize Extractor

        Args:
            page: Patchright Page Instance
        """
        self._page = page
        self._prev_screenshot: str | None = None
        self._comparator = ScreenshotComparator(page.context)

    async def extract_full_text(self, selector: str = "") -> str:
        """Extract all page text (supports iframe traversal and Markdown semantic conversion)."""
        js_script = f"""
            (selector) => {{
                const PASSWORD_SELECTOR = `{PASSWORD_FIELD_SELECTOR}`;

                function isHidden(node) {{
                    if (node.nodeType !== Node.ELEMENT_NODE) return false;
                    const style = window.getComputedStyle(node);
                    return style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0';
                }}

                function nodeToMarkdown(node) {{
                    if (node.nodeType === Node.TEXT_NODE) {{
                        return node.textContent.replace(/\\s+/g, ' ');
                    }}
                    if (node.nodeType !== Node.ELEMENT_NODE) return "";
                    if (isHidden(node)) return "";

                    const tag = node.tagName.toUpperCase();
                    if (['SCRIPT', 'STYLE', 'NOSCRIPT', 'CANVAS'].includes(tag)) {{
                        return "";
                    }}
                    if (tag === 'SVG') {{
                        let svgText = "";
                        node.querySelectorAll('text, tspan').forEach(el => {{
                            const t = el.textContent.trim();
                            if (t) svgText += t + " ";
                        }});
                        return svgText ? "[SVG: " + svgText.trim() + "] " : "";
                    }}

                    if (node.matches(PASSWORD_SELECTOR)) {{
                        return " [PASSWORD HIDDEN] ";
                    }}

                    let md = "";
                    let prefix = "";
                    let suffix = "";

                    if (tag === 'H1') prefix = "\\n# ";
                    else if (tag === 'H2') prefix = "\\n## ";
                    else if (tag === 'H3') prefix = "\\n### ";
                    else if (tag === 'H4') prefix = "\\n#### ";
                    else if (tag === 'H5') prefix = "\\n##### ";
                    else if (tag === 'H6') prefix = "\\n###### ";
                    else if (tag === 'LI') prefix = "\\n- ";
                    else if (tag === 'P' || tag === 'DIV' || tag === 'ARTICLE' || tag === 'SECTION') prefix = "\\n";
                    else if (tag === 'TR') prefix = "| ";

                    md += prefix;
                    if (node.shadowRoot) {{
                        for (let child of node.shadowRoot.childNodes) {{
                            md += nodeToMarkdown(child);
                        }}
                    }}
                    for (let child of node.childNodes) {{
                        md += nodeToMarkdown(child);
                    }}

                    if (tag === 'TD' || tag === 'TH') md += " | ";
                    if (tag === 'A' && node.href && node.href.startsWith('http')) {{
                        md += ` [Link: ${{node.href}}] `;
                    }}
                    if (tag === 'TR') md += "\\n";
                    if (tag === 'TABLE') md += "\\n";

                    return md + suffix;
                }}

                let targetElements = [];
                if (selector) {{
                    try {{
                        targetElements = Array.from(document.querySelectorAll(selector));
                    }} catch (e) {{
                        targetElements = [document.body];
                    }}
                }} else {{
                    targetElements = [document.body];
                }}

                let result = "";
                targetElements.forEach(el => {{
                    if (el) result += nodeToMarkdown(el);
                }});
                return result.trim();
            }}
        """

        full_text = ""
        for i, frame in enumerate(self._page.frames):
            try:
                frame_text = await frame.evaluate(js_script, selector)
                if frame_text and len(frame_text.strip()) > 0:
                    if i > 0:
                        full_text += f"\\n\\n--- Frame {i} Content ---\\n"
                    full_text += frame_text
            except Exception as exc:
                logger.debug("Extractor: could not extract text from frame %d: %s", i, exc)

        import re

        full_text = re.sub(r"\\n{3,}", "\\n\\n", full_text).strip()

        logger.info("Extractor: extracted full markdown length: %d", len(full_text))
        return full_text

    async def extract_screenshot(self, retina: bool = False) -> str:
        """Extract a page screenshot (base64-encoded JPEG).

        Args:
            retina: Whether to use 2x DPR (Retina high resolution).

        Returns:
            Base64-encoded JPEG image.
        """
        if retina:
            await self._set_device_scale_factor(2.0)

        # Redact password fields in screenshot to prevent privacy leaks
        password_locator = self._page.locator(PASSWORD_FIELD_SELECTOR)

        screenshot_bytes = await self._page.screenshot(
            type="jpeg",
            quality=_SCREENSHOT_QUALITY,
            full_page=False,
            mask=[password_locator],
        )

        if retina:
            await self._set_device_scale_factor(1.0)

        screenshot_base64 = base64.b64encode(screenshot_bytes).decode("utf-8")
        self._prev_screenshot = screenshot_base64

        logger.info("Extractor: captured screenshot (%d bytes)", len(screenshot_base64))
        return screenshot_base64

    async def compare_screenshots(
        self,
        baseline: str,
        strategy: Literal["fast", "accurate", "auto"] = "auto",
        similarity_threshold: float = 0.9,
        color_tolerance: float = 0.1,
        mismatch_threshold: float = 5.0,
        include_aa: bool = True,
    ) -> FastComparisonResult | AccurateComparisonResult:
        """Compare the current screenshot against a baseline screenshot.

        Args:
            baseline: Base64-encoded baseline screenshot.
            strategy: Comparison strategy.
                - 'auto': auto-select (based on image size, <800x600 uses accurate, otherwise fast)
                - 'fast': dHash fast detection (~2ms), returns similarity
                - 'accurate': Canvas API pixel-level comparison (~100ms), returns a diff image
            similarity_threshold: Fast strategy similarity threshold (0.0-1.0, default 0.9).
            color_tolerance: Accurate strategy color tolerance (0.0-1.0, default 0.1).
            mismatch_threshold: Accurate strategy mismatch threshold (0-100, default 5.0).
            include_aa: Whether accurate strategy enables anti-aliasing detection (default True).

        Returns:
            FastComparisonResult: when strategy is 'fast' or auto picks fast.
            AccurateComparisonResult: when strategy is 'accurate' or auto picks accurate.

        Raises:
            ValueError: if strategy is not 'fast', 'accurate', or 'auto'.
        """
        current = await self.extract_screenshot()

        return await self._comparator.compare(
            baseline=baseline,
            current=current,
            strategy=strategy,
            similarity_threshold=similarity_threshold,
            color_tolerance=color_tolerance,
            mismatch_threshold=mismatch_threshold,
            include_aa=include_aa,
        )

    async def compare_screenshot(self) -> str:
        """Compare the current screenshot with the previous one (convenience method).

        Returns:
            Text description of the comparison result.

        Raises:
            RuntimeError: if there is no previous screenshot.
        """
        if self._prev_screenshot is None:
            raise RuntimeError("No previous screenshot to compare with. Call extract_screenshot first.")

        result = await self.compare_screenshots(self._prev_screenshot, strategy="fast")
        return result.to_llm_message()

    async def export_pdf(self, path: str, *, include_metadata: bool = True) -> str:
        """Export the current page as a PDF file.

        Args:
            path: Destination file path for the exported PDF.
            include_metadata: Inject source URL, date, and page numbers into
                header/footer. Also enables print_background for faithful
                visual reproduction.

        Returns:
            Confirmation message with the output path.
        """
        if include_metadata:
            await self._page.pdf(
                path=path,
                print_background=True,
                display_header_footer=True,
                header_template=_PDF_HEADER_TEMPLATE,
                footer_template=_PDF_FOOTER_TEMPLATE,
                margin=_PDF_MARGIN,
            )
        else:
            await self._page.pdf(path=path, print_background=True)
        logger.info("Extractor: exported PDF to %s", path)
        return f"Exported PDF to {path}"

    async def detect_significant_visual_content(self) -> bool:
        """Detect if the page contains significant visual content (large Canvas/SVG/img).

        Returns True if visual elements with meaningful dimensions exist,
        indicating the page likely renders content visually rather than via DOM text.
        """
        js = """
            () => {
                const canvases = document.querySelectorAll('canvas');
                for (const c of canvases) {
                    if (c.width > 200 && c.height > 100) return true;
                    const rect = c.getBoundingClientRect();
                    if (rect.width > 200 && rect.height > 100) return true;
                }
                const svgs = document.querySelectorAll('svg');
                for (const s of svgs) {
                    const rect = s.getBoundingClientRect();
                    if (rect.width > 200 && rect.height > 100) return true;
                }
                return false;
            }
        """
        try:
            return bool(await self._page.evaluate(js))
        except Exception:
            return False

    async def extract_media(
        self, selector: str = "", max_images: int = 50, max_videos: int = 20, max_audios: int = 10
    ) -> str:
        """Extract all high-value media resource URLs from the page.

        Collects images (including lazy-loaded), videos, audio, and OG/Twitter meta
        images. Filters out icons, logos, and tiny decorative elements.

        Args:
            selector: CSS selector to scope extraction (empty = full page)
            max_images: Maximum number of images to return
            max_videos: Maximum number of videos to return
            max_audios: Maximum number of audio items to return
        """
        return await extract_page_media(self._page, selector, max_images, max_videos, max_audios)

    async def _set_device_scale_factor(self, scale: float) -> None:
        """Set the device scale factor (CDP).

        Args:
            scale: Scale factor (1.0 = normal, 2.0 = Retina).
        """
        try:
            cdp = await self._page.context.new_cdp_session(self._page)
            await cdp.send(
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": _SCREENSHOT_MAX_WIDTH,
                    "height": _SCREENSHOT_MAX_HEIGHT,
                    "deviceScaleFactor": scale,
                    "mobile": False,
                },
            )
            await cdp.detach()
        except Exception as exc:
            logger.warning(f"Extractor: failed to set DPR: {exc}")
