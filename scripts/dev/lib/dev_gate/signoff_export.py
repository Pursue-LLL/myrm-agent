"""Export durable coordinator signoff artifacts for audit and recovery (P0-D)."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from dev_gate.store import DevGateStore


def _optional_health_snapshot() -> dict[str, object]:
    health: dict[str, object] = {}
    try:
        from dev_gate.status import dev_gate_status  # noqa: PLC0415

        health["devGate"] = dev_gate_status()
    except ImportError:
        pass
    try:
        from e2e_core.host_resource_governor import (  # noqa: PLC0415
            host_resource_governor_snapshot,
            recent_transition_log,
        )

        health["hostGovernor"] = host_resource_governor_snapshot()
        health["hostGovernorTransitions"] = recent_transition_log(limit=16)
    except ImportError:
        pass
    return health


def build_signoff_artifact(
    store: DevGateStore,
    *,
    session_ids: tuple[str, ...] | None = None,
    session_limit: int = 200,
    event_limit: int = 2000,
) -> dict[str, object]:
    """Collect coordinator state for signoff audit without mutating the store."""
    if session_ids:
        sessions = tuple(
            record
            for record in (
                store.get(session_id)
                for session_id in session_ids
                if session_id.strip()
            )
            if record is not None
        )
        scoped_ids = tuple(record.session_id for record in sessions)
    else:
        sessions = store.list_recent_sessions(limit=session_limit)
        scoped_ids = tuple(record.session_id for record in sessions)
    events = store.fetch_recent_events(limit=event_limit, session_ids=scoped_ids)
    ownership = store.list_ownership_resources(session_ids=scoped_ids)
    return {
        "schema_version": 1,
        "exported_at": time.time(),
        "store_path": str(store.path),
        "session_scope": list(scoped_ids),
        "journal": store.journal_stats(),
        "sessions": [record.to_dict() for record in sessions],
        "events": list(events),
        "ownership_resources": list(ownership),
        "health": _optional_health_snapshot(),
    }


def export_signoff_artifact(
    store: DevGateStore,
    output_path: Path,
    *,
    session_ids: tuple[str, ...] | None = None,
    session_limit: int = 200,
    event_limit: int = 2000,
) -> dict[str, object]:
    """Write signoff artifact JSON and return export metadata."""
    artifact = build_signoff_artifact(
        store,
        session_ids=session_ids,
        session_limit=session_limit,
        event_limit=event_limit,
    )
    target = output_path.expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(artifact, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return {
        "output_path": str(target),
        "session_count": len(artifact["sessions"]),
        "event_count": len(artifact["events"]),
        "exported_at": artifact["exported_at"],
    }


def verify_signoff_artifact(path: Path) -> dict[str, object]:
    """Validate exported artifact structure for recovery checks."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("signoff artifact root must be an object")
    schema_version = payload.get("schema_version")
    if schema_version != 1:
        raise ValueError(f"unsupported signoff artifact schema: {schema_version!r}")
    sessions = payload.get("sessions")
    events = payload.get("events")
    if not isinstance(sessions, list):
        raise ValueError("sessions must be a list")
    if not isinstance(events, list):
        raise ValueError("events must be a list")
    journal = payload.get("journal")
    if not isinstance(journal, dict):
        raise ValueError("journal must be an object")
    return {
        "valid": True,
        "session_count": len(sessions),
        "event_count": len(events),
        "exported_at": payload.get("exported_at"),
        "store_path": payload.get("store_path"),
    }
