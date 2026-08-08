"""HTML email body → Markdown for wiki source sync.

[INPUT]
- myrm_agent_harness.toolkits.web_fetch.html_to_markdown::HTML2Markdown (POS: HTML→Markdown converter)

[OUTPUT]
- html_body_to_markdown: normalize Gmail HTML bodies before raw publish

[POS]
Shared HTML conversion helper for wiki Gmail ingest. Uses the same converter params as email channel.
"""

from __future__ import annotations


def html_body_to_markdown(html: str) -> str:
    """Convert email HTML body to clean Markdown for LLM consumption."""
    if not html:
        return ""
    from myrm_agent_harness.toolkits.web_fetch.html_to_markdown import HTML2Markdown

    converter = HTML2Markdown()
    converter.update_params(ignore_images=True)
    return converter.handle(html).strip()
