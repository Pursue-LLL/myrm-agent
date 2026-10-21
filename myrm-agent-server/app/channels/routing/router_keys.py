"""Stable string keys for routing maps (active tasks, approvals, session markers, context enclaves).

[OUTPUT]
- routing_session_key
- routing_enclave_key
- parse_enclave_key

[POS]
``routing_session_key`` builds legacy ``f"{channel}:{peer_id}"`` for DM/group peer maps.
``routing_enclave_key`` builds standard 4-tuple enclave isolation key:
``f"{tenant_id}:{channel}:{peer_id}:{agent_profile_id}"`` to prevent multi-agent/multi-tenant context contamination.
"""

from __future__ import annotations


def routing_session_key(channel: str, peer_id: str) -> str:
    """Return legacy map key ``f"{channel}:{peer_id}"`` for backward compatibility."""
    return f"{channel}:{peer_id}"


def routing_enclave_key(
    channel: str,
    peer_id: str,
    *,
    tenant_id: str = "default",
    agent_profile_id: str = "default",
) -> str:
    """Return the 4-tuple enclave isolation key ``tenant_id:channel:peer_id:agent_profile_id``.

    Ensures zero cross-talk between tenants, channels, senders, and different Agent profiles.
    """
    clean_tenant = (tenant_id or "default").strip() or "default"
    clean_channel = (channel or "unknown").strip() or "unknown"
    clean_peer = (peer_id or "anonymous").strip() or "anonymous"
    clean_agent = (agent_profile_id or "default").strip() or "default"
    return f"{clean_tenant}:{clean_channel}:{clean_peer}:{clean_agent}"


def parse_enclave_key(enclave_key: str) -> dict[str, str]:
    """Parse a 4-tuple enclave key back into its constituent components."""
    parts = enclave_key.split(":")
    if len(parts) >= 4:
        return {
            "tenant_id": parts[0],
            "channel": parts[1],
            "peer_id": ":".join(parts[2:-1]),
            "agent_profile_id": parts[-1],
        }
    if len(parts) == 2:
        return {
            "tenant_id": "default",
            "channel": parts[0],
            "peer_id": parts[1],
            "agent_profile_id": "default",
        }
    return {
        "tenant_id": "default",
        "channel": "unknown",
        "peer_id": enclave_key,
        "agent_profile_id": "default",
    }

