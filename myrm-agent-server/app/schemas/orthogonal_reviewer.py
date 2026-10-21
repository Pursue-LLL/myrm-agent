from pydantic import BaseModel, Field


class ReviewFindingDTO(BaseModel):
    finding_id: str
    reviewer: str
    severity: str
    category: str
    title: str
    description: str
    file_path: str
    line_range: str = Field(default="")
    suggestion: str


class ReviewerReportDTO(BaseModel):
    perspective: str
    findings: list[ReviewFindingDTO] = Field(default_factory=list)
    passed: bool
    summary: str
    execution_time_ms: float = Field(ge=0.0)


class ArbitrationVerdictDTO(BaseModel):
    session_id: str
    is_approved: bool
    status: str
    max_severity: str | None = None
    merged_findings: list[ReviewFindingDTO] = Field(default_factory=list)
    deduplicated_count: int = Field(default=0, ge=0)
    auto_fix_prompts: list[str] = Field(default_factory=list)
    summary: str


class IntentReviewRequest(BaseModel):
    task_prompt: str = Field(min_length=1)
    architecture_plan: str = Field(default="")
    code_diff: str = Field(min_length=1)
    files_touched: list[str] = Field(default_factory=list)


class BlindReviewRequest(BaseModel):
    code_diff: str = Field(min_length=1)
    files_touched: list[str] = Field(default_factory=list)
    public_signatures: list[str] | None = None


class ArbitrateRequest(BaseModel):
    session_id: str = Field(min_length=1)
    report_a: ReviewerReportDTO
    report_b: ReviewerReportDTO


class FullReviewRequest(BaseModel):
    session_id: str = Field(min_length=1)
    task_prompt: str = Field(min_length=1)
    architecture_plan: str = Field(default="")
    code_diff: str = Field(min_length=1)
    files_touched: list[str] = Field(default_factory=list)
    public_signatures: list[str] | None = None


class FullReviewResponse(BaseModel):
    session_id: str
    report_a: ReviewerReportDTO
    report_b: ReviewerReportDTO
    verdict: ArbitrationVerdictDTO


class AutoFixRequest(BaseModel):
    finding_ids: list[str] = Field(default_factory=list)


class AutoFixResponse(BaseModel):
    session_id: str
    applied_count: int
    remaining_critical_count: int
    fix_summary: str
