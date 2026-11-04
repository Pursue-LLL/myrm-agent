"""Data schemas for the Wiki five-layer document listing.

[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- WikiLayerItem

[POS]
Domain schema for per-layer document summaries.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WikiLayerItem(BaseModel):
    """Summary of a single markdown document within a wiki layer."""

    slug: str = Field(..., description="Document slug or filename")
    title: str = Field(..., description="Document title")
    relative_path: str = Field(..., description="Relative path within wiki vault")
    publish_status: str = Field("published", description="draft or published")
    updated_at: str = Field("", description="Last modified ISO timestamp")
    content_snippet: str = Field("", description="First few lines of document body")
