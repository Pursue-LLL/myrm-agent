"""Shared constants for agent-initiated outbound notifications.

[INPUT]
- (none — pure constants)

[OUTPUT]
- NOTIFY_SOURCE_AGENT, METADATA_KEY_NOTIFY_SOURCE: SSOT for agent notify metadata

[POS]
Outbound notify metadata constants shared by sender and channel bus wiring.
"""

from __future__ import annotations

NOTIFY_SOURCE_AGENT = "agent_notify"
METADATA_KEY_NOTIFY_SOURCE = "notify_source"
