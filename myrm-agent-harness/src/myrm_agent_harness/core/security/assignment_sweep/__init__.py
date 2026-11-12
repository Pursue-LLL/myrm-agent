"""Secret assignment sweep package: quoted-key and separator-prefix credential assignment detection with database URL auditing.

[INPUT]
- core.security.assignment_sweep.database_url_auditor::DatabaseUrlAuditor (POS: Database-URL leg of the assignment sweep: recognizes connection URIs that carry credentials and decides whether each is an exempt local-development DSN or a leak; only a loopback host with a standard development credential pair is exempt.)
- core.security.assignment_sweep.quoted_sweep_engine::AssignmentMatch, QuotedKeySecretAssignmentSweepEngine, find_assignment_matches (POS: Assignment-detection core of the sweep: finds quoted, bracketed and plain key-value assignments of sensitive keys, drops placeholders and benign code symbols, and folds the database-URL audit into one verdict (clean, suspected leak or exempted local dev).)
- core.security.assignment_sweep.types::AssignmentFormat, AssignmentKeyFamily, AssignmentSweepFinding, AssignmentSweepReport, AssignmentSweepVerdict, DatabaseUrlAuditResult (POS: Contract layer of the assignment sweep: the key-family, notation and verdict enums plus the finding, report and DSN-audit models shared by the sweep engine and the database URL auditor.)

[OUTPUT]
- the sweep engine, the one-line match helper, the database URL auditor and the domain types listed in `__all__`

[POS]
Package facade of the assignment sweep: the single import point for the sweep engine, the one-line match helper, the
database URL auditor and the domain types.
"""

from __future__ import annotations

from .database_url_auditor import DatabaseUrlAuditor
from .quoted_sweep_engine import AssignmentMatch, QuotedKeySecretAssignmentSweepEngine, find_assignment_matches
from .types import (
    AssignmentFormat,
    AssignmentKeyFamily,
    AssignmentSweepFinding,
    AssignmentSweepReport,
    AssignmentSweepVerdict,
    DatabaseUrlAuditResult,
)

__all__ = [
    "AssignmentFormat",
    "AssignmentKeyFamily",
    "AssignmentMatch",
    "AssignmentSweepFinding",
    "AssignmentSweepReport",
    "AssignmentSweepVerdict",
    "DatabaseUrlAuditResult",
    "DatabaseUrlAuditor",
    "QuotedKeySecretAssignmentSweepEngine",
    "find_assignment_matches",
]
