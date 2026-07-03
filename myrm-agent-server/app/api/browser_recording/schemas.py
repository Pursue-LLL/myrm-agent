"""Request/response schemas for Browser Recording API.


[INPUT]
- pydantic::BaseModel, Field

[OUTPUT]
- RecordingStepResponse: single recorded action step
- RecordingSessionResponse: recording session summary
- GenerateSkillRequest: skill generation request
- GenerateSkillResponse: generated skill result

[POS]
Pydantic schema definitions for Browser Recording API endpoints.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class RecordingStepResponse(BaseModel):
    """Single recorded action step."""

    seq: int
    action: str
    selector: str
    value: str = ""
    url: str = ""
    title: str = ""
    timestamp: float = 0.0
    element_text: str = ""
    element_role: str = ""
    is_password: bool = False
    screenshot_b64: str | None = None


class RecordingSessionResponse(BaseModel):
    """Recording session summary."""

    session_id: str
    status: str
    start_url: str = ""
    step_count: int = 0
    steps: list[RecordingStepResponse] = Field(default_factory=list)


class GenerateSkillRequest(BaseModel):
    """Request to generate a Browser Skill from recorded steps."""

    session_id: str = Field(description="Recording session ID")
    skill_name: str = Field(description="Name for the generated skill", pattern=r"^[a-zA-Z][a-zA-Z0-9_-]*$")
    description: str = Field(default="", description="Optional description override")


class GenerateSkillResponse(BaseModel):
    """Response from skill generation."""

    skill_id: str
    skill_name: str
    description: str
    step_count: int
    credential_placeholders: list[str] = Field(default_factory=list)
