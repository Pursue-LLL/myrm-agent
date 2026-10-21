"""Wiki browser clip multipart payload measurement.

[INPUT]
- (none)

[OUTPUT]
- MAX_CLIP_PAYLOAD_BYTES: int — 8MB multipart cap for POST /wiki/clip
- clip_form_payload_bytes: measure all form text fields + uploaded asset bytes

[POS] server.services.wiki.clip — clip upload size guard (extension multipart)
"""

from __future__ import annotations

MAX_CLIP_PAYLOAD_BYTES = 8 * 1024 * 1024


def clip_form_payload_bytes(
    *,
    source_url: str,
    title: str,
    clip_mode: str,
    html: str,
    markdown: str,
    folder_path: str,
    queue_compile: str,
    asset_urls: str,
    asset_file_bytes: tuple[bytes, ...],
) -> int:
    return (
        len(source_url.encode("utf-8"))
        + len(title.encode("utf-8"))
        + len(clip_mode.encode("utf-8"))
        + len(html.encode("utf-8"))
        + len(markdown.encode("utf-8"))
        + len(folder_path.encode("utf-8"))
        + len(queue_compile.encode("utf-8"))
        + len(asset_urls.encode("utf-8"))
        + sum(len(chunk) for chunk in asset_file_bytes)
    )
