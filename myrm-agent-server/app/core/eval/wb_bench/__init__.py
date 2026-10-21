"""WorkBuddy Bench adapter package facade.

[INPUT]
- wb_bench.download::list_wb_bench_sources, ensure_wb_bench_source (POS: WBBench data source layer)
- wb_bench.workspace::build_wb_bench_cases (POS: WBBench task/workspace builder)

[OUTPUT]
- Public WBBench API surface re-exported so existing
  ``from app.core.eval.wb_bench import ...`` call sites keep working unchanged.

[POS]
Aggregation facade for the WorkBuddy Bench adapter sub-package. Keeps
`download` (data source), `workspace` (task building) and `verifier` (grading
wiring) as single-responsibility modules while exposing one stable package
boundary to the eval service and API layer.
"""

from __future__ import annotations

from . import download, verifier, workspace
from .download import (
    ARCHIVES_DIR,
    SOURCES_DIR,
    WB_BENCH_ROOT,
    WB_BENCH_SUBSETS,
    WORKSPACES_DIR,
    DownloadAbortedError,
    WbBenchSubset,
    ensure_wb_bench_source,
    list_wb_bench_sources,
)
from .workspace import build_wb_bench_cases

__all__ = [
    "download",
    "verifier",
    "workspace",
    "ARCHIVES_DIR",
    "SOURCES_DIR",
    "WB_BENCH_ROOT",
    "WB_BENCH_SUBSETS",
    "WORKSPACES_DIR",
    "DownloadAbortedError",
    "WbBenchSubset",
    "build_wb_bench_cases",
    "ensure_wb_bench_source",
    "list_wb_bench_sources",
]
