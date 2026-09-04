"""Wiki services for myrm-agent-server business layer.

[INPUT]
- .memory_to_wiki::MemoryToWikiArchiver (POS: Memory→Wiki automatic archiving)

[OUTPUT]
- MemoryToWikiArchiver: wiki archiving facade for API / background consumers

[POS]
Top-level wiki facade. Domain subpackages (vault / maintain / obsidian /
source_sync / clip / knowledge_pack) live under this package and expose their own facades.
"""

from __future__ import annotations

from .memory_to_wiki import MemoryToWikiArchiver

__all__ = ["MemoryToWikiArchiver"]
