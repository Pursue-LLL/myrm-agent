"""Cross-process ledger of E2E session-owned CDP pages.

[INPUT]
- register/unregister calls from the two page-create authority points
  (browser_orchestrator client RPC wrapper, chrome_mcp publish point)
- wave lease ledger (wave-orchestrator.json) for lease-bound protection
- owner process identity (pid + OS start token)

[OUTPUT]
- protected_target_ids() — union of live session pages + infra + AOS anchor
- prune_dead_session_pages() — close pages whose owner died and lease lapsed
- list_session_pages() / ledger_readable()

[POS]
Session page ownership SSOT. The orchestrator keeps its `ownedPages` only in
daemon memory and the wave ledger carries no targetId, so no other component
could answer "which physical page belongs to a live session". Without this
ledger every page-hygiene judgement (unbound drift, stray blank budget, orphan
prune) either mis-reads a healthy plane or is silently vacuous.
"""

from __future__ import annotations

import fcntl
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from e2e_core.real_user_home import real_user_home


class SessionPageTarget(TypedDict):
    targetId: str
    sessionId: str
    leaseId: str
    ownerPid: int
    ownerProcessStart: str
    url: str
    registeredAt: float


def _state_dir() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    return Path(override) if override else real_user_home() / ".local/state/myrm-dev"


def _ledger_path() -> Path:
    return _state_dir() / "session-page-targets.json"


@contextmanager
def _locked_ledger() -> Iterator[Path]:
    ledger = _ledger_path()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.with_suffix(".lock").open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield ledger
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _coerce(item: object) -> SessionPageTarget | None:
    if not isinstance(item, dict):
        return None
    target_id = item.get("targetId")
    owner_pid = item.get("ownerPid")
    if not isinstance(target_id, str) or not target_id.strip():
        return None
    if not isinstance(owner_pid, int):
        return None
    registered = item.get("registeredAt")
    return {
        "targetId": target_id.strip(),
        "sessionId": str(item.get("sessionId", "")),
        "leaseId": str(item.get("leaseId", "")),
        "ownerPid": owner_pid,
        "ownerProcessStart": str(item.get("ownerProcessStart", "")),
        "url": str(item.get("url", "")),
        "registeredAt": float(registered) if isinstance(registered, (int, float)) else 0.0,
    }


def _read(path: Path) -> list[SessionPageTarget] | None:
    """Return records, or None when the ledger exists yet cannot be parsed."""
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, list):
        return None
    return [record for item in payload if (record := _coerce(item)) is not None]


def _write(path: Path, records: list[SessionPageTarget]) -> None:
    if not records:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(records, separators=(",", ":")) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


def register_session_page(
    target_id: str,
    *,
    session_id: str = "",
    lease_id: str = "",
    url: str = "",
    owner_pid: int | None = None,
) -> None:
    """Record ownership of a session page (idempotent per targetId)."""
    target = target_id.strip()
    if not target:
        return
    pid = owner_pid if owner_pid is not None else os.getpid()
    from dev_gate.owner_identity import capture_owner_process_start  # noqa: PLC0415

    with _locked_ledger() as ledger:
        existing = _read(ledger)
        records = [] if existing is None else existing
        record: SessionPageTarget = {
            "targetId": target,
            "sessionId": session_id.strip(),
            "leaseId": lease_id.strip(),
            "ownerPid": pid,
            "ownerProcessStart": capture_owner_process_start(pid),
            "url": url.strip(),
            "registeredAt": time.time(),
        }
        _write(
            ledger,
            [item for item in records if item["targetId"] != target] + [record],
        )


def unregister_session_pages(target_ids: str | Iterable[str]) -> None:
    """Drop ownership records once the owner closed the page (or gave up on it)."""
    if isinstance(target_ids, str):
        candidates = {target_ids.strip()}
    else:
        candidates = {str(item).strip() for item in target_ids if str(item).strip()}
    if not candidates:
        return
    with _locked_ledger() as ledger:
        records = _read(ledger)
        if records is None:
            return
        _write(ledger, [item for item in records if item["targetId"] not in candidates])


def _read_locked() -> list[SessionPageTarget] | None:
    """Single locked read: records, or None when a present ledger is unparseable."""
    with _locked_ledger() as ledger:
        return _read(ledger)


def list_session_pages() -> list[SessionPageTarget]:
    return _read_locked() or []


def ledger_readable() -> bool:
    """False when a ledger file is present but unparseable (fail-closed signal)."""
    return _read_locked() is not None


def _owner_alive(record: SessionPageTarget) -> bool:
    from dev_gate.owner_identity import owner_process_matches  # noqa: PLC0415

    return owner_process_matches(
        pid=int(record["ownerPid"]),
        expected_start=str(record.get("ownerProcessStart", "")),
    )


def _active_lease_ids() -> set[str] | None:
    """Active wave lease ids; None when the wave ledger is unreadable."""
    state_dir = Path(
        os.getenv("MYRM_DEV_STATE_DIR", "").strip()
        or str(real_user_home() / ".local/state/myrm-dev")
    )
    try:
        payload = json.loads(
            (state_dir / "wave-orchestrator.json").read_text(encoding="utf-8")
        )
    except FileNotFoundError:
        return set()
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    wave = payload.get("wave")
    if not isinstance(wave, dict) or str(wave.get("status", "")).strip() != "open":
        return set()
    now = datetime.now(tz=UTC)
    active: set[str] = set()
    for item in payload.get("leases") or []:
        if not isinstance(item, dict) or str(item.get("status", "")) != "active":
            continue
        lease_id = str(item.get("leaseId", "")).strip()
        raw_expiry = str(item.get("expiresAt", "")).strip()
        if not lease_id or not raw_expiry:
            continue
        try:
            expiry = datetime.fromisoformat(raw_expiry.replace("Z", "+00:00"))
        except ValueError:
            continue
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if expiry > now:
            active.add(lease_id)
    return active


def protected_session_target_ids() -> set[str] | None:
    """Target ids still owned by a live session; None when protection is unverifiable.

    A page stays protected while either its owning process runs or its wave
    lease is still active — the two independent liveness signals a session has.
    An unreadable ledger fails closed (None), never open: reporting "no claims"
    for ownership data nobody could read would let hygiene close live pages.
    """
    records = _read_locked()
    if records is None:
        return None
    if not records:
        return set()
    lease_ids = _active_lease_ids()
    if lease_ids is None:
        return None
    protected: set[str] = set()
    for record in records:
        if record["leaseId"] and record["leaseId"] in lease_ids:
            protected.add(record["targetId"])
            continue
        if _owner_alive(record):
            protected.add(record["targetId"])
    return protected


def _close_exact_target(cdp_port: int, target_id: str) -> bool:
    url = f"http://127.0.0.1:{cdp_port}/json/close/{target_id}"
    try:
        with urllib.request.urlopen(url, timeout=3) as response:
            response.read()
        return True
    except urllib.error.HTTPError as exc:
        return exc.code == 404
    except (OSError, urllib.error.URLError):
        return False


def prune_dead_session_pages(
    *, cdp_port: int, session_ids: frozenset[str] | None = None
) -> tuple[int, int]:
    """Close pages whose owner process died and whose lease lapsed; drop records.

    Only a lease-bound page is provably finished: an active lease or a live
    owner each independently vouch for the page, and a page created without a
    lease (shared run-id / diagnostic sessions) is left to its own session
    destroy rather than reclaimed on owner death alone.

    ``session_ids`` narrows the sweep to one session's own pages for callers that
    must not touch a peer's leftovers. Dead-owner detection is pid + OS start
    token, so a recycled pid never keeps a corpse protected nor exposes a live
    page.
    """
    leases = _active_lease_ids()
    if leases is None:
        return 0, 0
    with _locked_ledger() as ledger:
        records = _read(ledger)
        if records is None:
            return 0, 0
        dead: list[SessionPageTarget] = []
        for record in records:
            if session_ids is not None and record["sessionId"] not in session_ids:
                continue
            if not record["leaseId"] or record["leaseId"] in leases:
                continue
            if _owner_alive(record):
                continue
            dead.append(record)
        if not dead:
            return 0, 0
        closed_ids: set[str] = set()
        failed = 0
        for record in dead:
            if _close_exact_target(cdp_port, record["targetId"]):
                closed_ids.add(record["targetId"])
            else:
                failed += 1
        # A failed close keeps its record so a later sweep retries it, but the
        # dead owner must not keep the page protected forever.
        _write(
            ledger,
            [item for item in records if item["targetId"] not in closed_ids],
        )
    return len(closed_ids), failed


def prune_dead_session_pages_for_session(
    session_id: str, *, cdp_port: int
) -> tuple[int, int]:
    token = session_id.strip()
    if not token:
        return 0, 0
    return prune_dead_session_pages(cdp_port=cdp_port, session_ids=frozenset({token}))
