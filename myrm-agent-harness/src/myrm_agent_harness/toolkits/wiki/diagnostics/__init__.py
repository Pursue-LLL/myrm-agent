"""Wiki diagnostics — deterministic quality measurement.

[INPUT]
- .structural_lint::collect_structural_lint_snapshot (POS: zero-LLM structural lint)

[OUTPUT]
- StructuralLintSnapshot: aggregate counts for structural lint issues
- collect_broken_link_issues: scans and returns broken markdown link issues
- collect_invalid_frontmatter_type_issues: scans and returns invalid frontmatter type issues
- collect_structural_lint_snapshot: collects full structural lint snapshot

[POS]
Wiki diagnostics entry point. Re-exports the deterministic structural lint tooling.
"""

from myrm_agent_harness.toolkits.wiki.diagnostics.structural_lint import (
    StructuralLintSnapshot,
    collect_broken_link_issues,
    collect_invalid_frontmatter_type_issues,
    collect_structural_lint_snapshot,
)

__all__ = [
    "StructuralLintSnapshot",
    "collect_broken_link_issues",
    "collect_invalid_frontmatter_type_issues",
    "collect_structural_lint_snapshot",
]
