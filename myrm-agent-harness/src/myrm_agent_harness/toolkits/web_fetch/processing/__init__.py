"""Content processing pipeline utilities for web fetch.

[INPUT]
- processing.pipeline (POS: HTML/JSON/XML to Markdown pipeline) [lazy]
- processing.spill (POS: UECD spill wrapper for large pages)

[OUTPUT]
- Re-exports: ContentPipeline (loaded on first access, with the HTML parser it needs)

[POS]
Subpackage entry for post-fetch content processing and markdown conversion. Importing a submodule such as ``spill``
does not load the HTML pipeline.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import ContentPipeline

__all__ = ["ContentPipeline"]


def __getattr__(name: str) -> object:
    """Load the pipeline on first access."""
    if name == "ContentPipeline":
        from myrm_agent_harness.toolkits.web_fetch.processing.pipeline import ContentPipeline

        globals()[name] = ContentPipeline
        return ContentPipeline
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
