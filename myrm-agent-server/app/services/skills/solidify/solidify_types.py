"""[INPUT] Pydantic models for skill solidification and external preview contracts.
[OUTPUT] Strong-typed schemas for parameter minimization, 4-in-1 asset bundling, and clean preview.
[POS] app/services/skills/solidify/solidify_types.py.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class ParameterExtractionRule(BaseModel):
    """Dynamic parameter definition for minimized skill execution."""

    name: str = Field(..., description="Parameter key, e.g. 'topic', 'author'")
    description: str = Field(..., description="Explanation of what this parameter controls")
    default_value: Optional[str] = Field(None, description="Optional default value")
    placeholder_pattern: str = Field(..., description="Placeholder expression, e.g. '{{topic}}'")
    required: bool = Field(True, description="Whether parameter is mandatory")


class SolidifySkillRequest(BaseModel):
    """Payload to solidify current artifact and chat deliverables into a reusable skill."""

    name: str = Field(..., description="Skill machine-readable identifier, e.g. 'interactive-courseware'")
    display_title: str = Field(..., description="Human friendly title for display")
    description: str = Field(..., description="Summary of skill purpose and output capability")
    category: str = Field("education", description="Skill category, e.g. 'education', 'presentation', 'data'")
    source_artifact_content: str = Field(..., description="Raw HTML, markdown, or code of refined deliverable")
    source_artifact_type: str = Field("html", description="Artifact format, e.g. 'html', 'markdown', 'svg'")
    custom_parameters: Optional[List[ParameterExtractionRule]] = Field(
        None, description="Explicit parameters specified or refined by the user"
    )
    include_plan_before_execute_hint: bool = Field(
        True, description="Whether generated instructions mandate structured planning before generation"
    )


class SkillAssetBundle(BaseModel):
    """Standard 4-in-1 directory bundle for solidified skill."""

    skill_md_content: str = Field(..., description="Full SKILL.md file with YAML frontmatter")
    template_content: str = Field(..., description="Template file in assets/ with minimized placeholders")
    example_content: str = Field(..., description="Static polished example in assets/example.html")
    reference_md_content: Optional[str] = Field(None, description="Optional style guidelines in references/")
    relative_paths: List[str] = Field(default_factory=list, description="Relative paths inside skill bundle")


class SolidifySkillResponse(BaseModel):
    """Result of skill solidification."""

    skill_id: str = Field(..., description="Created unique skill ID")
    name: str = Field(..., description="Machine-readable name")
    display_title: str = Field(..., description="Display title")
    description: str = Field(..., description="Skill description")
    parameters: List[ParameterExtractionRule] = Field(default_factory=list, description="Extracted dynamic parameters")
    bundle_files: List[str] = Field(default_factory=list, description="List of generated files in the bundle")
    preview_url: Optional[str] = Field(None, description="External clean preview URL for testing")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")


class ExternalPreviewCreateRequest(BaseModel):
    """Request to create an isolated clean external preview."""

    content: str = Field(..., description="HTML or SVG content to render in external browser")
    content_type: str = Field("text/html", description="MIME content type")
    title: str = Field("Deliverable Preview", description="Page title")


class ExternalPreviewMetadata(BaseModel):
    """Metadata tracking external browser clean preview instances."""

    preview_id: str = Field(..., description="Unique preview token/identifier")
    title: str = Field(..., description="Preview title")
    content_type: str = Field("text/html", description="MIME content type")
    view_url: str = Field(..., description="Direct clean preview route path")
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="Creation timestamp",
    )
