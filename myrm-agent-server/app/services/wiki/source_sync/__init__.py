"""Wiki external source sync — deterministic pull into raw/ (zero LLM).

[INPUT]
- app.services.wiki.source_sync.runner (POS: wiki pull orchestration SSOT)
- app.services.wiki.source_sync.schemas (POS: source sync DTOs)

[OUTPUT]
- Public subpackage for wiki source sync; consumers import runner / schemas /
  config_store / state_store directly.

[POS]
Public package for wiki source sync, documenting the package boundary and
keeping ``source_sync`` importable as a package.
"""

from __future__ import annotations
