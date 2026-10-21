"""Block 0 probe for ClawHub-compatible registry mirrors (delegates to harness SSOT).

[INPUT]
- myrm_agent_harness.agent.skills.market.sources.clawhub_registry (POS: Probe SSOT)

[OUTPUT]
- probe_clawhub_registry, probe_configured_cn_mirror re-exports

[POS]
Thin server adapter for ClawHub registry mirror health probes.
"""

from __future__ import annotations

from myrm_agent_harness.agent.skills.market.sources.clawhub_registry import (
    probe_clawhub_registry,
    probe_configured_cn_mirror,
)

__all__ = ["probe_clawhub_registry", "probe_configured_cn_mirror"]
