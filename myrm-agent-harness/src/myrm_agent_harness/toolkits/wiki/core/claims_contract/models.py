"""[INPUT]
- pydantic::BaseModel / Field (POS: 校验与序列化)

[OUTPUT]
- WikiEvidence / WikiClaim / EvidenceSnapshotStatus

[POS]
`wiki/core/claims_contract/` 的 claim/evidence 数据模型；字段即 frontmatter 契约。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    pass

CLAIM_STATUSES = frozenset({"supported", "contested", "unsupported", "unknown"})

EvidenceSnapshotStatus = Literal["verified", "stale", "missing"]

MAX_EVIDENCE_EXCERPT_CHARS = 2000

RAW_BYTES_LRU_MAX_BYTES = 32 * 1024 * 1024

@dataclass(frozen=True, slots=True)
class WikiEvidence:
    """Evidence pointer backing a wiki claim."""

    kind: str
    source_id: str
    path: str
    lines: str
    weight: float
    confidence: float
    note: str
    content_sha256: str = ""
    updated_at: str = ""

@dataclass(frozen=True, slots=True)
class WikiClaim:
    """Structured belief entry stored in concept frontmatter."""

    id: str
    text: str
    status: str
    confidence: float
    evidence: tuple[WikiEvidence, ...]
    updated_at: str = ""
