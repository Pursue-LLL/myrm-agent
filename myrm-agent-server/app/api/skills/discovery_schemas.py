"""Skill discovery API request/response schemas.

[INPUT]
pydantic::BaseModel (POS: Schema validation)

[OUTPUT]
Request/response models for skill discovery endpoints.

[POS]
Pydantic schemas extracted from discovery.py to stay within
the 400-line file budget.
"""

from __future__ import annotations

from pydantic import BaseModel


class SkillSearchResultResponse(BaseModel):
    id: str
    name: str
    description: str
    source: str
    author: str
    install_url: str
    install_method: str
    version: str = ""
    stars: int = 0
    downloads: int = 0
    tags: list[str] = []
    readme_url: str | None = None
    subdirectory: str | None = None
    installed_version: str = ""
    upgrade_available: bool = False
    installed_skill_id: str = ""


class SkillSearchResponse(BaseModel):
    results: list[SkillSearchResultResponse]
    total: int
    query: str


class SkillInstallRequest(BaseModel):
    skill_id: str
    source: str
    agent_id: str | None = None
    mount_to_agent: bool = True


class SkillInstallResponse(BaseModel):
    success: bool
    skill_name: str = ""
    skill_id: str = ""
    installed_path: str = ""
    error: str = ""
    error_code: str = ""
    mounted: bool = False
    mount_agent_id: str = ""
    mount_skill_id: str = ""
    mount_already_present: bool = False
    mount_error: str = ""
    allowlist_appended: bool = False
    allowlist_append_error: str = ""


class SkillUpdateInfoResponse(BaseModel):
    skill_name: str
    current_version: str
    remote_version: str
    source: str
    skill_id: str
    has_update: bool


class UpdateCheckResponse(BaseModel):
    has_updates: bool
    updates: list[SkillUpdateInfoResponse]


class SkillUpdateRequest(BaseModel):
    skill_name: str
    skill_id: str
    source: str


class SkillUninstallRequest(BaseModel):
    skill_id: str
    force: bool = False


class SkillPreviewRequest(BaseModel):
    skill_id: str
    source: str


class ScanFindingResponse(BaseModel):
    threat_type: str
    severity: int
    description: str
    line_number: int | None = None


class SkillPreviewResponse(BaseModel):
    skill_id: str
    name: str
    description: str
    version: str
    files: list[str]
    scan_findings: list[ScanFindingResponse] = []
    is_clean: bool = True


class SkillInstallFromUrlRequest(BaseModel):
    url: str
    agent_id: str | None = None
    mount_to_agent: bool = True


class SkillUrlInfo(BaseModel):
    url: str
    name: str
    description: str = ""
    is_installed: bool


class SkillAnalyzeUrlResponse(BaseModel):
    urls: list[SkillUrlInfo]


class CustomSourceRequest(BaseModel):
    url: str
    source_type: str = "well-known"
    label: str = ""


class CustomSourceResponse(BaseModel):
    url: str
    source_type: str
    label: str
    healthy: bool


class CustomSourceListResponse(BaseModel):
    sources: list[CustomSourceResponse]


class CustomSourceProbeResponse(BaseModel):
    reachable: bool
    skill_count: int
    url: str
