"""Third-party assistant asset detection and ingestion toolkit.

Detects Hermes / Claude Code / Codex configurations on the host and translates their
memories, skills and rules into Myrm's standard layout. Whole-instance backup and
cross-device restore are not part of this package (see ``infra.state_archive``).
Strict typing applied: No `Any` types allowed.

[INPUT]
- toolkits.memory.sovereign_migration.competitor_adapter::CompetitorIngestionAdapter (POS: Universal
  competitor ingestion and translation adapter (Hermes, Claude Code, Codex).)
- toolkits.memory.sovereign_migration.types::CompetitorDetectResult, CompetitorImportResult, CompetitorType
  (POS: Type definitions for competitor asset detection and ingestion.)

[OUTPUT]
- Package facade re-exporting 4 public names: CompetitorDetectResult, CompetitorImportResult,
  CompetitorIngestionAdapter, CompetitorType

[POS]
Third-party assistant asset detection and ingestion toolkit.
"""

from __future__ import annotations

from myrm_agent_harness.toolkits.memory.sovereign_migration.competitor_adapter import (
    CompetitorIngestionAdapter,
)
from myrm_agent_harness.toolkits.memory.sovereign_migration.types import (
    CompetitorDetectResult,
    CompetitorImportResult,
    CompetitorType,
)

__all__ = [
    "CompetitorDetectResult",
    "CompetitorImportResult",
    "CompetitorIngestionAdapter",
    "CompetitorType",
]
