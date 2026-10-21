"""
[INPUT]
- Pydantic BaseModel for slide elements, slides structure, and presentation artifacts.

[OUTPUT]
- SlideLayoutType, SlideElementType
- SlideElement, SlideData
- PresentationGenerateRequest, PresentationArtifactResponse

[POS]
Pydantic data models for EnterprisePresentationSlideGeneratorAndVisualConceptIllustrator.
Single file < 120 lines. Strictly typed.
"""

from typing import List, Literal, Optional

from pydantic import BaseModel, Field

SlideLayoutType = Literal[
    "title_hero",
    "two_column_comparison",
    "three_card_flow",
    "concept_illustration_focus",
    "summary_action",
]

SlideElementType = Literal[
    "text",
    "card",
    "vector_metrics",
    "concept_illustration",
    "comparison_column",
]


class SlideElement(BaseModel):
    element_type: SlideElementType
    title: Optional[str] = None
    body: Optional[str] = None
    bullet_points: Optional[List[str]] = Field(default_factory=list)
    illustration_prompt: Optional[str] = None
    illustration_url: Optional[str] = None
    metric_value: Optional[str] = None
    metric_label: Optional[str] = None


class SlideData(BaseModel):
    slide_number: int
    title: str
    subtitle: Optional[str] = None
    layout: SlideLayoutType
    elements: List[SlideElement] = Field(default_factory=list)
    speaker_notes: Optional[str] = None


class PresentationGenerateRequest(BaseModel):
    topic: str = Field(..., min_length=2, max_length=200, description="Presentation topic or theme")
    template_style: Literal[
        "enterprise_blue",
        "minimal_dark",
        "creative_gradient",
        "tech_emerald",
    ] = Field("enterprise_blue", description="Theme and visual styling preset")
    slides_count: int = Field(5, ge=3, le=15, description="Number of slides to generate")
    enable_illustrations: bool = Field(True, description="Whether to include AI concept illustration placeholders")


class PresentationArtifactResponse(BaseModel):
    id: str
    topic: str
    template_style: str
    total_slides: int
    slides: List[SlideData]
    file_name: str
    file_size_bytes: int
    download_url: str
    created_at: str
