"""Full-content delivery plan for web_fetch: one shared budget, one truncation window per long page

[INPUT]
- utils.context_format::format_document_header (POS: Source header shared by every context-formatting path)
- utils.truncation_window::truncation_window, apply_truncation_window, TruncationWindow (POS: Where head+tail truncation cuts)
- core.security.detection.content_boundary::wrap_untrusted (POS: UNTRUSTED_DATA boundary) [lazy]

[OUTPUT]
- FetchedPage: one fetched page (source URL, title, Markdown body)
- ReadRange: omitted lines of the stored copy, labelled with the page they belong to
- FullContentDelivery: the model-visible text, the full text to persist, and the omitted-line ranges
- plan_full_content(): split the shared budget fairly, cut each long page, and locate the omitted lines
- clamp_read_ranges(): drop the ranges a capped stored copy no longer holds
- all_failed_content(): tool result when no URL could be read
- MAX_LINE_CHARS: longest line kept in the stored copy of a cut page

[POS]
Pure layout logic for web_fetch's full-content mode. Every page gets an equal share of one character budget, a page
shorter than its share keeps all of it, and each longer page is cut head+tail inside its own share, so every page reaches
the model. The text to persist uses the same layout, which makes the line ranges of the omitted parts exact.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import NamedTuple

from myrm_agent_harness.utils.context_format import format_document_header
from myrm_agent_harness.utils.truncation_window import TruncationWindow, apply_truncation_window, truncation_window

MIN_BUDGET_CHARS = 12_000
PER_PAGE_BUDGET_CHARS = 3_000
MAX_BUDGETED_PAGES = 5
# file_read_tool clamps every line at 2,000 chars; staying below keeps each character of a cut page readable.
MAX_LINE_CHARS = 1_900
_WRAP_SEARCH_FRACTION = 0.3
_BLOCK_FRAME_CHARS = 4  # "\n\n" after the header and after the body
_MAX_FAILED_URL_CHARS = 200
_FAILED_LEAD = "[web_fetch]: Could not retrieve content from:"


@dataclass(frozen=True, slots=True)
class FetchedPage:
    url: str
    title: str
    body: str


class ReadRange(NamedTuple):
    """Closed, 1-indexed line range of the stored copy that holds the part of one page the model cannot see."""

    label: str
    first_line: int
    last_line: int


@dataclass(frozen=True, slots=True)
class FullContentDelivery:
    """What to show, what to persist, and where the omitted parts sit in the persisted text."""

    visible_text: str
    stored_text: str | None
    read_ranges: tuple[ReadRange, ...]
    raw_chars: int

    @property
    def truncated(self) -> bool:
        return self.stored_text is not None


def plan_full_content(pages: Sequence[FetchedPage], failed_urls: Sequence[str] = ()) -> FullContentDelivery:
    """Lay out ``pages`` within one budget; ``stored_text`` is set only when some page had to be cut."""
    headers = [
        format_document_header(index, page.url, page.title, include_title=True, include_date=False)
        for index, page in enumerate(pages, start=1)
    ]
    bodies = [page.body for page in pages]
    budget = max(MIN_BUDGET_CHARS, PER_PAGE_BUDGET_CHARS * min(len(pages), MAX_BUDGETED_PAGES))
    failures = _failure_block(failed_urls)

    sizes = _block_sizes(headers, bodies)
    if sum(sizes) <= budget:
        return _in_full(headers, bodies, failures)

    # file_read_tool numbers lines after universal-newline translation, so line numbers only match the stored copy
    # once CR and CRLF are LF, in the headers (a page title can hold them) as well as in the bodies.
    headers = [_normalize_newlines(header) for header in headers]
    bodies = [_normalize_newlines(body) for body in bodies]
    sizes = _block_sizes(headers, bodies)
    if sum(sizes) <= budget:
        return _in_full(headers, bodies, failures)

    shares = _fair_shares(sizes, budget)
    bodies = [
        _soft_wrap(body) if size > share else body for body, size, share in zip(bodies, sizes, shares, strict=True)
    ]
    first_body_lines = _first_body_lines(headers, bodies)

    visible_bodies = list(bodies)
    ranges: list[ReadRange] = []
    for index, (header, body, size, share) in enumerate(zip(headers, bodies, sizes, shares, strict=True)):
        if size <= share:
            continue
        window = truncation_window(body, share - len(header) - _BLOCK_FRAME_CHARS)
        if window is None or window.head_end >= window.tail_start:
            continue
        omitted = _omitted_lines(body, window, first_body_lines[index])
        if omitted is None:
            continue
        visible_bodies[index] = apply_truncation_window(body, window)
        ranges.append(ReadRange(f"【{index + 1}】", *omitted))

    if not ranges:
        return _in_full(headers, bodies, failures)

    stored_text = _join_blocks(headers, bodies)
    return FullContentDelivery(
        visible_text=_join_blocks(headers, visible_bodies) + failures,
        stored_text=stored_text,
        read_ranges=tuple(ranges),
        raw_chars=len(stored_text),
    )


def clamp_read_ranges(ranges: Sequence[ReadRange], total_lines: int) -> list[ReadRange]:
    """Keep the ranges that start inside a stored copy of ``total_lines`` lines, ending them at its last line."""
    return [r._replace(last_line=min(r.last_line, total_lines)) for r in ranges if r.first_line <= total_lines]


def all_failed_content(failed_urls: Sequence[str]) -> str:
    """Tool result when no URL could be read; the URL list sits inside the untrusted boundary, the guidance outside."""
    from myrm_agent_harness.core.security.detection.content_boundary import wrap_untrusted

    return (
        "[web_fetch]: Could not retrieve content from the requested URL(s):\n"
        f"{wrap_untrusted(_failure_listing(failed_urls), source='web_fetch')}\n"
        "The target page(s) may be unavailable (HTTP 404/403/timeout). "
        "Please synthesize the final answer using search snippets or other available information."
    )


def _in_full(headers: Sequence[str], bodies: Sequence[str], failures: str) -> FullContentDelivery:
    pages_text = _join_blocks(headers, bodies)
    return FullContentDelivery(
        visible_text=pages_text + failures, stored_text=None, read_ranges=(), raw_chars=len(pages_text)
    )


def _join_blocks(headers: Sequence[str], bodies: Sequence[str]) -> str:
    return "".join(f"{header}\n\n{body}\n\n" for header, body in zip(headers, bodies, strict=True))


def _block_sizes(headers: Sequence[str], bodies: Sequence[str]) -> list[int]:
    return [len(header) + len(body) + _BLOCK_FRAME_CHARS for header, body in zip(headers, bodies, strict=True)]


def _fair_shares(sizes: Sequence[int], budget: int) -> list[int]:
    """Max-min fair split: a block below the equal share keeps its full size, the rest split what remains equally."""
    shares = [0] * len(sizes)
    pending = sorted(range(len(sizes)), key=lambda index: sizes[index])
    remaining = budget
    while pending:
        equal = remaining // len(pending)
        smallest = pending[0]
        if sizes[smallest] > equal:
            for index in pending:
                shares[index] = equal
            break
        shares[smallest] = sizes[smallest]
        remaining -= sizes[smallest]
        pending.pop(0)
    return shares


def _first_body_lines(headers: Sequence[str], bodies: Sequence[str]) -> list[int]:
    """1-indexed line of each body's first line within the stored copy (header lines and two frame newlines precede)."""
    first_lines: list[int] = []
    line = 1
    for header, body in zip(headers, bodies, strict=True):
        first_lines.append(line + header.count("\n") + 2)
        line += header.count("\n") + body.count("\n") + _BLOCK_FRAME_CHARS
    return first_lines


def _omitted_lines(body: str, window: TruncationWindow, first_body_line: int) -> tuple[int, int] | None:
    """Closed line range holding every omitted character; a line cut in the middle is included so it can be read whole."""
    first = first_body_line + body.count("\n", 0, window.head_end)
    if body[window.head_end] == "\n":
        first += 1  # the head ends exactly where a line ends
    last = first_body_line + body.count("\n", 0, window.tail_start)
    if body[window.tail_start - 1] == "\n":
        last -= 1  # the tail starts exactly where a line starts
    return (first, last) if first <= last else None


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _soft_wrap(text: str) -> str:
    return "\n".join(_wrap_line(line) for line in text.split("\n"))


def _wrap_line(line: str) -> str:
    """Break a line longer than ``MAX_LINE_CHARS`` at whitespace near the limit, or hard at the limit without any."""
    if len(line) <= MAX_LINE_CHARS:
        return line
    pieces: list[str] = []
    start = 0
    while len(line) - start > MAX_LINE_CHARS:
        end = start + MAX_LINE_CHARS
        floor = start + int(MAX_LINE_CHARS * (1 - _WRAP_SEARCH_FRACTION))
        cut = max(line.rfind(" ", floor, end + 1), line.rfind("\t", floor, end + 1))
        if cut == -1:
            pieces.append(line[start:end])
            start = end
        else:
            pieces.append(line[start:cut])
            start = cut + 1
    pieces.append(line[start:])
    return "\n".join(pieces)


def _failure_listing(urls: Sequence[str]) -> str:
    """One ``- <url>`` line per distinct URL; they come from the model or a page, so drop control characters and cap."""
    cleaned = (("".join(ch for ch in url if ch.isprintable()))[:_MAX_FAILED_URL_CHARS] for url in urls)
    return "\n".join(f"- {url}" for url in dict.fromkeys(url for url in cleaned if url))


def _failure_block(failed_urls: Sequence[str]) -> str:
    listing = _failure_listing(failed_urls)
    return f"{_FAILED_LEAD}\n{listing}\n\n" if listing else ""
