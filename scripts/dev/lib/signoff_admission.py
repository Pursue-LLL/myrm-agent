"""Signoff Admission Orchestrator (SAO) — instant admit/defer for maintenance signoff gates.

[INPUT]
- peer_count_ssot::chrome_e2e_pytest_peer_count
- mux_load::solo_gate_active_mux_peer_count (via peer_count_ssot)
- e2e_lease_liveness::load_wave_snapshot

[OUTPUT]
- build_signoff_admission_snapshot() → e2e-context signoffAdmission block
- admit_or_defer() → ADMITTED | DEFERRED (<1s, no blind sleep)

[POS]
Replaces blind SOLO_WAIT / master-lock sleep loops (roadmap §14). Daily ./myrm test bypasses SAO.
"""

from __future__ import annotations

import os
import sqlite3
import time
import uuid
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypedDict

from peer_count_ssot import chrome_e2e_pytest_peer_count, solo_gate_active_mux_peer_count


class EpisodeState(StrEnum):
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SignoffAdmissionDict(TypedDict, total=False):
    state: str
    holder: str | None
    holderPid: int | None
    deferReason: str | None
    soloClear: bool
    retryAfterSec: int
    queueDepth: int
    next_action: str
    peers: int
    waveLeases: int
    activeMux: int


@dataclass(frozen=True, slots=True)
class AdmitOrDeferResult:
    outcome: Literal["ADMITTED", "DEFERRED"]
    episode_id: str | None
    reason: str | None
    retry_after_sec: int
    holder: str | None
    holder_pid: int | None


def _state_dir() -> Path:
    override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override).resolve()
    return Path.home() / ".local/state/myrm-dev"


def _db_path() -> Path:
    return _state_dir() / "signoff-admission.sqlite"


def _legacy_master_lock_dir() -> Path:
    return _state_dir() / "chrome-e2e-signoff.master.lockdir"


def _legacy_master_lock_owner() -> tuple[str | None, int | None]:
    lock_dir = _legacy_master_lock_dir()
    pid_file = lock_dir / "pid"
    if not pid_file.is_file():
        return None, None
    raw = pid_file.read_text(encoding="utf-8").strip()
    if not raw.isdigit():
        return None, None
    pid = int(raw)
    try:
        os.kill(pid, 0)
    except OSError:
        return None, None
    return "legacy-master-lock", pid


def _connect() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS signoff_episodes (
            episode_id TEXT PRIMARY KEY,
            episode_kind TEXT NOT NULL,
            label TEXT NOT NULL,
            owner_pid INTEGER NOT NULL,
            state TEXT NOT NULL,
            submitted_at REAL NOT NULL,
            started_at REAL NOT NULL,
            finished_at REAL NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_signoff_episodes_state
            ON signoff_episodes(state);
        """
    )
    return conn


def _reconcile_stale_episodes(conn: sqlite3.Connection) -> None:
    rows = conn.execute(
        "SELECT episode_id, owner_pid FROM signoff_episodes WHERE state = ?",
        (EpisodeState.RUNNING.value,),
    ).fetchall()
    now = time.time()
    for row in rows:
        pid = int(row["owner_pid"])
        try:
            os.kill(pid, 0)
        except OSError:
            conn.execute(
                """
                UPDATE signoff_episodes
                SET state = ?, finished_at = ?
                WHERE episode_id = ?
                """,
                (EpisodeState.CANCELLED.value, now, row["episode_id"]),
            )
    conn.commit()


def _wave_active_leases() -> int:
    try:
        from e2e_lease_liveness import load_wave_snapshot, wave_lease_counts

        counts = wave_lease_counts(load_wave_snapshot())
        return int(counts.effective_total)
    except ImportError:
        return 0


def solo_cluster_clear_for_signoff() -> tuple[bool, str]:
    peers = chrome_e2e_pytest_peer_count()
    if peers != 0:
        return False, f"chrome_e2e_peers={peers}"
    leases = _wave_active_leases()
    if leases > 0:
        return False, f"wave_leases={leases}"
    mux = solo_gate_active_mux_peer_count()
    if mux > 1:
        return False, f"active_mux={mux}"
    return True, ""


@dataclass(frozen=True, slots=True)
class RunningEpisode:
    episode_id: str
    episode_kind: str
    label: str
    owner_pid: int


def _running_episode(conn: sqlite3.Connection) -> RunningEpisode | None:
    row = conn.execute(
        """
        SELECT episode_id, episode_kind, label, owner_pid
        FROM signoff_episodes
        WHERE state = ?
        ORDER BY started_at ASC
        LIMIT 1
        """,
        (EpisodeState.RUNNING.value,),
    ).fetchone()
    if row is not None:
        return RunningEpisode(
            episode_id=str(row["episode_id"]),
            episode_kind=str(row["episode_kind"]),
            label=str(row["label"]),
            owner_pid=int(row["owner_pid"]),
        )
    legacy_label, legacy_pid = _legacy_master_lock_owner()
    if legacy_label is None or legacy_pid is None:
        return None
    return RunningEpisode(
        episode_id=f"legacy-{legacy_pid}",
        episode_kind="legacy-master-lock",
        label=legacy_label,
        owner_pid=legacy_pid,
    )


def _default_retry_after_sec(*, solo_clear: bool, has_holder: bool) -> int:
    if has_holder:
        return 30
    if not solo_clear:
        return 30
    return 5


def build_signoff_admission_snapshot() -> SignoffAdmissionDict:
    peers = chrome_e2e_pytest_peer_count()
    leases = _wave_active_leases()
    mux = solo_gate_active_mux_peer_count()
    solo_clear, solo_reason = solo_cluster_clear_for_signoff()

    holder: str | None = None
    holder_pid: int | None = None
    queue_depth = 0

    try:
        with _connect() as conn:
            _reconcile_stale_episodes(conn)
            running = _running_episode(conn)
            if running is not None:
                holder = running.label
                holder_pid = running.owner_pid
            pending = conn.execute(
                """
                SELECT COUNT(*) AS c FROM signoff_episodes
                WHERE state = ?
                """,
                (EpisodeState.RUNNING.value,),
            ).fetchone()
            if pending is not None:
                queue_depth = int(pending["c"])
    except sqlite3.Error:
        legacy_label, legacy_pid = _legacy_master_lock_owner()
        holder = legacy_label
        holder_pid = legacy_pid

    if holder is not None:
        state = "RUNNING"
        defer_reason = f"signoff_holder_active:{holder}"
        next_action = "SIGNOFF_DEFER"
    elif not solo_clear:
        state = "DEFERRED"
        defer_reason = f"solo_cluster_busy:{solo_reason}"
        next_action = "SIGNOFF_DEFER"
    else:
        state = "READY"
        defer_reason = None
        next_action = "SIGNOFF_ADMIT_OK"

    retry = _default_retry_after_sec(solo_clear=solo_clear, has_holder=holder is not None)

    return SignoffAdmissionDict(
        state=state,
        holder=holder,
        holderPid=holder_pid,
        deferReason=defer_reason,
        soloClear=solo_clear,
        retryAfterSec=retry,
        queueDepth=queue_depth,
        next_action=next_action,
        peers=peers,
        waveLeases=leases,
        activeMux=mux,
    )


def admit_or_defer(*, episode_kind: str, label: str) -> AdmitOrDeferResult:
    owner_pid = os.getpid()
    solo_clear, solo_reason = solo_cluster_clear_for_signoff()

    with _connect() as conn:
        _reconcile_stale_episodes(conn)
        running = _running_episode(conn)
        if running is not None:
            return AdmitOrDeferResult(
                outcome="DEFERRED",
                episode_id=None,
                reason=f"signoff_holder_active:{running.label}",
                retry_after_sec=30,
                holder=running.label,
                holder_pid=running.owner_pid,
            )

        if not solo_clear:
            return AdmitOrDeferResult(
                outcome="DEFERRED",
                episode_id=None,
                reason=f"solo_cluster_busy:{solo_reason}",
                retry_after_sec=30,
                holder=None,
                holder_pid=None,
            )

        now = time.time()
        episode_id = f"{episode_kind}-{uuid.uuid4().hex[:12]}"
        conn.execute(
            """
            INSERT INTO signoff_episodes (
                episode_id, episode_kind, label, owner_pid, state,
                submitted_at, started_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                episode_id,
                episode_kind,
                label,
                owner_pid,
                EpisodeState.RUNNING.value,
                now,
                now,
            ),
        )
        conn.commit()

    return AdmitOrDeferResult(
        outcome="ADMITTED",
        episode_id=episode_id,
        reason=None,
        retry_after_sec=0,
        holder=label,
        holder_pid=owner_pid,
    )


def complete_episode(
    episode_id: str,
    *,
    outcome: Literal["SUCCEEDED", "FAILED", "CANCELLED"],
) -> bool:
    now = time.time()
    with _connect() as conn:
        cur = conn.execute(
            """
            UPDATE signoff_episodes
            SET state = ?, finished_at = ?
            WHERE episode_id = ? AND state = ?
            """,
            (outcome, now, episode_id, EpisodeState.RUNNING.value),
        )
        conn.commit()
        return cur.rowcount == 1


def admit_or_defer_to_dict(*, episode_kind: str, label: str) -> dict[str, object]:
    result = admit_or_defer(episode_kind=episode_kind, label=label)
    payload: dict[str, object] = {
        "outcome": result.outcome,
        "retryAfterSec": result.retry_after_sec,
        "holder": result.holder,
        "holderPid": result.holder_pid,
        "reason": result.reason,
        "episodeId": result.episode_id,
    }
    if result.outcome == "DEFERRED":
        print(
            f"SIGNOFF_DEFERRED: kind={episode_kind} reason={result.reason} "
            f"retry_after_sec={result.retry_after_sec} holder={result.holder or 'none'}"
        )
    else:
        print(
            f"SIGNOFF_ADMITTED: kind={episode_kind} episode_id={result.episode_id} "
            f"label={label} pid={result.holder_pid}"
        )
    return payload
