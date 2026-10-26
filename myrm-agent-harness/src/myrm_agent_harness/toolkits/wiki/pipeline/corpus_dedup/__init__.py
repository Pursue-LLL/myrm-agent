"""Raw corpus deduplication governance for wiki compile prerequisites.

[INPUT]
- .eligibility::CorpusEligibilityFilter (POS: blocked-path filter for compile/queue/stale)
- .governor::CorpusDedupGovernor (POS: deduplication actions governor and compile hold release)
- .scanner::CorpusDedupScanner (POS: incremental fingerprint scanner)
- .snippets::build_group_body_snippets (POS: duplicate member preview builder)
- .store::CorpusDedupStore (POS: SQLite persistence for deduplication state)
- .types::DedupStats, DedupTier, DispositionAction, DuplicateGroup, FileEnqueuer (POS: data contracts)

[OUTPUT]
- CorpusDedupGovernor, CorpusDedupScanner, CorpusDedupStore, CorpusEligibilityFilter, build_group_body_snippets

[POS]
Raw Corpus Dedup 原始材料去重治理模块入口。提供三级排重指纹扫描、排重状态持久化、编译前置资格过滤，以及「先扫描后编译」的持久化编译暂扣（compile hold）。
"""

from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.eligibility import (
    CorpusEligibilityFilter,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.governor import (
    CorpusDedupGovernor,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.scanner import (
    CorpusDedupScanner,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.snippets import (
    build_group_body_snippets,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.store import (
    CorpusDedupStore,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
    DedupStats,
    DedupTier,
    DispositionAction,
    DispositionResult,
    DuplicateGroup,
    DuplicateMemberSnippet,
    ExcludedRawEntry,
    FileEnqueuer,
    GroupStatus,
    HeldFile,
    PlannedGroup,
    ScanProgress,
    ScanResult,
    TrashedRawEntry,
    VaultHygieneSnapshot,
)

__all__ = [
    "CorpusDedupGovernor",
    "CorpusDedupScanner",
    "CorpusDedupStore",
    "CorpusEligibilityFilter",
    "DedupStats",
    "DedupTier",
    "DispositionAction",
    "DispositionResult",
    "DuplicateGroup",
    "DuplicateMemberSnippet",
    "ExcludedRawEntry",
    "FileEnqueuer",
    "GroupStatus",
    "HeldFile",
    "PlannedGroup",
    "ScanProgress",
    "ScanResult",
    "TrashedRawEntry",
    "VaultHygieneSnapshot",
    "build_group_body_snippets",
]
