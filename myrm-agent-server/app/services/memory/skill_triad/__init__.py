"""Memory skill triad and physical scope isolation service module.

[POS]
Exports service provider and singleton accessor for scope physical partitioning,
provider degradation observability, machine CLI envelopes, and integration pipeline verification.

[INPUT]
- app.services.memory.skill_triad.provider

[OUTPUT]
- MemorySkillTriadProvider
- get_memory_skill_triad_provider
"""

from __future__ import annotations

from app.services.memory.skill_triad.provider import (
    MemorySkillTriadProvider,
    get_memory_skill_triad_provider,
)

__all__ = [
    "MemorySkillTriadProvider",
    "get_memory_skill_triad_provider",
]
