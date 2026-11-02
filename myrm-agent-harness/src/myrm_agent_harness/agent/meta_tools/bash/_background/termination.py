"""Process-group termination for background bash jobs.

A job leader starts in its own process group (``get_process_group_kwargs``), so the group id is the leader's pid, and
the group outlives the leader for as long as anything the job started keeps running (``nohup`` daemons, children that
inherited the pipes). Signalling by that id reaches them. POSIX hands the id to another process once the last member has
exited, so every signal of a stop goes through ``signal_group_if_ours``, which checks the id first. The leader is recorded
as ``(pid, start stamp)`` at registration (``utils.process_start``: a start time that a system clock step does not
move): only a process with a different start stamp holding that pid counts as a takeover (``leader_id_reassigned``), so
a leader that has exited and left a live group stays stoppable. A finished job's stop also needs the members recorded
when it ended: its id is accepted only while the group still holds one of them (``live_members``). A leader that
outlived the server that started it is stopped at the next start (``reap_orphaned_groups``) once the ledger's record of
that server proves it gone (no process holds its pid, or one with another start stamp does) and the leader is what the
ledger recorded: its start time (a wall-clock reading, so on Linux a clock step since then leaves the group running)
and its group leadership. Where the leader's parent is does not matter, so a subreaper such as ``systemd --user`` that
adopted it changes nothing. A job recorded without a server is left running.
A finished job's leftovers are remembered in memory only: after an exit that skips ``atexit`` (a crash, a forced
kill) the ledger shows the job as finished, so the next start neither lists nor stops what it left running.
Once a stop has signalled, it reads the group directly, which also reaches a process the job forks while it is being
stopped. A check and the signal that follows it are not atomic, a gap that no signal addressed by group id can close.
Out of reach: a process that started its own session has left the group, and a process that started after the last
look, once every recorded member had exited, is not found. A leader that could not be read at registration has no
recorded identity, so its id is used as it is. Windows has no group named after a pid (``GROUP_VISIBLE``): a stop kills
the leader's process tree there and does not list what is left.

[INPUT]
- psutil (POS: process table access that lists a group's live members and reads a process's start time and status)
- utils.os_compat::IS_WIN, SIGKILL, kill_spawned_group (POS: cross-platform process-group control: the platform flag, SIGKILL, and signalling the group a spawned child leads by its id)
- utils.process_start::start_stamp (POS: a process's start time that stays comparable across system clock adjustments)
- agent.meta_tools.bash._background.consume::BackgroundRegistryEntry (POS: live registry row with ring buffers, spill writer, the leader's recorded identity and the processes the job left running)

[OUTPUT]
- GROUP_VISIBLE: whether the platform can list a job's group (false on Windows)
- GroupMember: identity (pid + start stamp) of one process: a live member of a job's group, its leader, or the server that registered it
- leader_identity: a job leader's pid with its start stamp, read when the job is registered
- own_identity: this server's pid with its start stamp, recorded in the ledger on every job it registers
- LedgerLeader: a job leader as the ledger recorded it (pid, start time, and the server that registered the job)
- leader_id_reassigned: whether another process now holds a recorded leader's pid
- signal_group_if_ours: signal a job's group unless another process now holds the leader's pid
- snapshot_group_members: the live members of a job's group
- live_members: the members the group holds now, provided it is still the group a recorded member belongs to
- refresh_leftovers: the live members of a finished job's group, remembered on its entry
- stop_job: stop a running job and everything it started within one grace budget; nothing is signalled once its leader's pid belongs to another process
- stop_leftovers: stop what a finished job left behind
- reap_orphaned_groups: startup reclaim of job leaders whose recorded server is gone

[POS]
Group-level stop primitives of BackgroundProcessRegistry: every signal to a job's group is sent through
``signal_group_if_ours``; the startup reclaim checks the ledger instead. Listing a group needs a POSIX process table: on
Windows, which names no group after a pid, those listings are empty, the startup reclaim does nothing and a stop kills
the leader's process tree.
"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from collections.abc import Iterable
from contextlib import suppress
from dataclasses import dataclass
from typing import TYPE_CHECKING

import psutil

from myrm_agent_harness.utils.os_compat import IS_WIN, SIGKILL, kill_spawned_group
from myrm_agent_harness.utils.process_start import start_stamp

if TYPE_CHECKING:
    from myrm_agent_harness.agent.meta_tools.bash._background.consume import BackgroundRegistryEntry

logger = logging.getLogger(__name__)

# Bound on waiting for the leader to be reaped after a SIGKILL.
_REAP_LEADER_SECONDS = 2.0
_POLL_INTERVAL_SECONDS = 0.05
# SIGKILL cannot be caught, but the kernel still needs a moment to tear a process down.
_CONFIRM_SECONDS = 1.0
# One process reports the same start stamp on every read; the slack absorbs clock-tick rounding.
_SAME_PROCESS_TOLERANCE_SECONDS = 1.0
# The ledger stamps ``started_at`` right after spawn, a moment later than the process's own create time.
_LEADER_START_TOLERANCE_SECONDS = 2.0
_INIT_PID = 1
# Windows has no process group named after a pid, so no group can be listed there.
GROUP_VISIBLE = not IS_WIN


@dataclass(frozen=True, slots=True)
class GroupMember:
    """A process of a job (group member, leader or registering server), identified well enough to survive pid reuse."""

    pid: int
    start_stamp: float


def snapshot_group_members(pgid: int) -> tuple[GroupMember, ...]:
    """Live (non-zombie) processes whose process group is ``pgid``."""
    if not GROUP_VISIBLE or pgid <= _INIT_PID:
        return ()
    members: list[GroupMember] = []
    for pid in psutil.pids():
        try:
            if os.getpgid(pid) != pgid:
                continue
            proc = psutil.Process(pid)
            if proc.status() == psutil.STATUS_ZOMBIE:
                continue
            members.append(GroupMember(pid=pid, start_stamp=start_stamp(proc)))
        except (OSError, psutil.Error):
            continue
    return tuple(members)


def leader_identity(pid: int) -> GroupMember | None:
    """The job leader's pid with its start stamp, or ``None`` when no process can be read at ``pid``."""
    if pid <= _INIT_PID:
        return None
    try:
        return GroupMember(pid=pid, start_stamp=start_stamp(psutil.Process(pid)))
    except (OSError, psutil.Error):
        return None


def own_identity() -> GroupMember | None:
    """This server's pid with its start stamp, or ``None`` when it cannot be read (or is pid 1).

    Read on every registration rather than cached, so a forked child records itself and not the process it came from.
    """
    return leader_identity(os.getpid())


def leader_id_reassigned(leader: GroupMember | None) -> bool:
    """True when a process other than the recorded ``leader`` holds its pid, so the group id is no longer the job's.

    Only positive evidence counts. A leader that was never recorded, a pid nobody holds (the job's group can outlive its
    leader under that id) and a pid held by the leader itself all leave the id trusted.
    """
    if leader is None:
        return False
    try:
        holder = start_stamp(psutil.Process(leader.pid))
    except (OSError, psutil.Error):
        return False
    return abs(holder - leader.start_stamp) > _SAME_PROCESS_TOLERANCE_SECONDS


def signal_group_if_ours(pid: int, leader: GroupMember | None, sig: signal.Signals) -> bool:
    """Signal the group named ``pid`` unless another process holds that pid now.

    Returns False only when the signal was withheld for that reason; a group that has already ended is not a failure.
    The signal reaches whatever holds the id when it is sent, so the check comes right before it, every time.
    """
    if leader_id_reassigned(leader):
        logger.warning("background pid=%s now belongs to another process; no signal was sent", pid)
        return False
    with suppress(OSError):
        kill_spawned_group(pid, sig)
    return True


def live_members(pgid: int, known: Iterable[GroupMember]) -> tuple[GroupMember, ...]:
    """The processes group ``pgid`` holds now, if it is still the group that ``known`` belonged to.

    A scan that shares no process with ``known`` could be a stranger that was handed the group id after the last
    member exited, so it yields nothing and nothing gets signalled on its account. Nothing is scanned when ``known``
    is empty.
    """
    recorded = {member.pid: member.start_stamp for member in known}
    if not recorded:
        return ()
    current = snapshot_group_members(pgid)
    for member in current:
        stamp = recorded.get(member.pid)
        if stamp is not None and abs(member.start_stamp - stamp) <= _SAME_PROCESS_TOLERANCE_SECONDS:
            return current
    return ()


def refresh_leftovers(entry: BackgroundRegistryEntry) -> tuple[GroupMember, ...]:
    """The live members of a finished job's group, kept on the entry so the next look is checked against the latest."""
    live = live_members(entry.info.pid, entry.leftover_members)
    if live:
        entry.leftover_members = live
    return live


async def _wait_gone(pgid: int, deadline: float) -> tuple[GroupMember, ...]:
    """Poll until the group holds no process or ``deadline`` (monotonic) passes; return what is still alive."""
    alive = snapshot_group_members(pgid)
    while alive and time.monotonic() < deadline:
        await asyncio.sleep(_POLL_INTERVAL_SECONDS)
        alive = snapshot_group_members(pgid)
    return alive


async def _settle_group(pgid: int, leader: GroupMember | None, *, deadline: float) -> tuple[GroupMember, ...]:
    """Wait until ``deadline`` for the group to empty, SIGKILL it when it does not, return the survivors.

    The survivors are what the caller must report instead of claiming success. A group whose id another process holds
    by then is not the job's: nothing is signalled and nothing is reported.
    """
    alive = await _wait_gone(pgid, deadline)
    if not alive or not signal_group_if_ours(pgid, leader, SIGKILL):
        return ()
    return await _wait_gone(pgid, time.monotonic() + _CONFIRM_SECONDS)


async def stop_job(
    entry: BackgroundRegistryEntry,
    *,
    force: bool,
    grace_seconds: float,
) -> tuple[GroupMember, ...]:
    """Stop a running job: signal its group, wait for the leader, escalate, then settle the rest of the group.

    The leader's wait and the group's wait share one ``grace_seconds`` budget. Once signalled, the group is read
    directly, so a process forked while the stop is under way is waited for and killed like any other. A check of the
    leader's pid comes before each signal: once another process holds it, nothing further is signalled and nothing is
    reported as left behind. The wait that confirms the last SIGKILL checks nothing, so a process that takes the id
    then is listed among the survivors, unsignalled. Returns the members that survived even SIGKILL.
    """
    pid = entry.info.pid
    deadline = time.monotonic() + (0.0 if force else grace_seconds)
    if not signal_group_if_ours(pid, entry.leader, SIGKILL if force else signal.SIGTERM):
        return ()
    if not force and grace_seconds > 0:
        try:
            await asyncio.wait_for(entry.proc.wait(), timeout=max(0.0, deadline - time.monotonic()))
        except TimeoutError:
            logger.info(
                "background pid=%s did not exit within %.1fs of SIGTERM; escalating to SIGKILL",
                pid,
                grace_seconds,
            )
            if not signal_group_if_ours(pid, entry.leader, SIGKILL):
                return ()
            with suppress(TimeoutError):
                await asyncio.wait_for(entry.proc.wait(), timeout=_REAP_LEADER_SECONDS)
        except (ProcessLookupError, OSError):
            pass
    return await _settle_group(pid, entry.leader, deadline=deadline)


async def stop_leftovers(
    pgid: int,
    known: tuple[GroupMember, ...],
    leader: GroupMember | None,
    *,
    force: bool,
    grace_seconds: float,
) -> tuple[GroupMember, ...]:
    """Stop what a finished job left behind; nothing is signalled unless ``known`` still has a process in the group."""
    if not live_members(pgid, known):
        return ()
    if not signal_group_if_ours(pgid, leader, SIGKILL if force else signal.SIGTERM):
        return ()
    return await _settle_group(pgid, leader, deadline=time.monotonic() + (0.0 if force else grace_seconds))


@dataclass(frozen=True, slots=True)
class LedgerLeader:
    """A job leader as the ledger recorded it; ``owner`` is the server that registered the job, ``None`` if unrecorded."""

    pid: int
    started_at: float
    owner: GroupMember | None


def _owner_gone(owner: GroupMember | None) -> bool:
    """True only on positive evidence that the server that registered a job is no longer running.

    An unrecorded server, one that cannot be read and one that is still running (this process included) all count as
    present, so a doubt reclaims nothing.
    """
    if owner is None:
        return False
    try:
        proc = psutil.Process(owner.pid)
        if proc.status() == psutil.STATUS_ZOMBIE:
            return True
        return abs(start_stamp(proc) - owner.start_stamp) > _SAME_PROCESS_TOLERANCE_SECONDS
    except psutil.NoSuchProcess:
        return True
    except (OSError, psutil.Error):
        return False


def _is_orphaned_leader(leader: LedgerLeader) -> bool:
    """True when the server that registered the job is gone and ``leader.pid`` is the leader the ledger recorded."""
    if not GROUP_VISIBLE or leader.pid <= _INIT_PID or leader.pid == os.getpid() or not _owner_gone(leader.owner):
        return False
    try:
        proc = psutil.Process(leader.pid)
        return (
            abs(proc.create_time() - leader.started_at) <= _LEADER_START_TOLERANCE_SECONDS
            and os.getpgid(leader.pid) == leader.pid
            and proc.status() != psutil.STATUS_ZOMBIE
        )
    except (OSError, psutil.Error):
        return False


def reap_orphaned_groups(leaders: Iterable[LedgerLeader]) -> int:
    """SIGKILL the groups of job leaders whose server is gone; return how many groups were stopped.

    ``leaders`` are the jobs the ledger still shows as running after a restart. Anything that does not match on the
    server being gone, the recorded start time and group leadership is left alone: leaving a process running is
    recoverable, signalling a stranger is not.
    """
    reaped = 0
    for leader in leaders:
        if _is_orphaned_leader(leader):
            kill_spawned_group(leader.pid, SIGKILL)
            reaped += 1
    return reaped


__all__ = [
    "GROUP_VISIBLE",
    "GroupMember",
    "LedgerLeader",
    "leader_id_reassigned",
    "leader_identity",
    "live_members",
    "own_identity",
    "reap_orphaned_groups",
    "refresh_leftovers",
    "signal_group_if_ours",
    "snapshot_group_members",
    "stop_job",
    "stop_leftovers",
]
