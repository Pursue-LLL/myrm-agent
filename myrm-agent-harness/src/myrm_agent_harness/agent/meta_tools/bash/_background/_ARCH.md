# _background/

## Overview

Background bash process registry and durable job ledger for ``bash_code_execute_tool(run_in_background=True)`` and ``bash_process_tool``.

Stopping a job stops its whole process group (a process tree on Windows); each signal of a stop first checks that no other process holds the recorded leader's pid. Details and limits are in the header of ``termination.py``.

## File Index

| File | Role | Description | I/O/P |
|------|------|-------------|-------|
| __init__.py | Package | 域聚合出口：导出 registry 单例 + 快照类型（6 个公共符号）。 | ✅ |
| types.py | Core | Shared dataclasses (`BackgroundProcessInfo` incl. `leftover_processes`, `BackgroundQuotaError`, listener aliases). | ✅ |
| registry.py | Core | Process-wide singleton registry with per-session buckets, command credential redaction (`redact_command_line`), register (recording the leader's `(pid, start stamp)` and, in the ledger, this server's)/list/get, output reads, `wait_for_process`, stdin writes and the reader task (`_consume`). | ✅ |
| lifecycle.py | Core | `RegistryLifecycleMixin`: what ends a job entry — group-level SIGTERM→SIGKILL ``kill`` (a finished job is only asked to stop what it left behind), ``kill_session_jobs`` (running jobs only), the reap timer deferred while leftovers live, ``shutdown`` over the groups of running jobs and of finished jobs that left a live member (a job whose leader pid another process now holds is skipped). | ✅ |
| termination.py | Core | Group-level stop primitives; listing a group needs a POSIX process table (`GROUP_VISIBLE` is false on Windows, where no group is listed and a stop kills the leader's process tree): `leader_identity` records a leader as `(pid, start stamp)` and `leader_id_reassigned` is true only when a process with a different start stamp holds that pid; `signal_group_if_ours` is the one place a job's group is signalled from (the startup reconcile checks the ledger instead) and checks the leader's pid right before every signal; `snapshot_group_members` lists `(pid, start stamp)` per live member; `live_members` accepts a scan of a finished job's group only while a recorded member is still that very process; `refresh_leftovers` keeps an entry's record current; `stop_job` and `stop_leftovers` read the group directly once signalled (`stop_leftovers` checks the record first), SIGKILL what remains within one grace deadline (`stop_job` shares it between the leader and the group, `stop_leftovers` has no leader to wait for), return the survivors, and signal nothing further once the leader's pid belongs to another process; `own_identity` is this server's `(pid, start stamp)`, recorded in the ledger per job; `reap_orphaned_groups` for the startup reconcile stops a `LedgerLeader` only when the server the ledger recorded is gone (its pid unheld, a zombie, or held by a process with another start stamp) and the process is the recorded leader (start time, own group, not a zombie); a job recorded without a server, or whose server cannot be read, is left running. | ✅ |
| consume.py | Core | Per-entry stdout/stderr reader loop, spill hooks, 10Hz adaptive progress throttle (with 100% terminal penetration & trailing flush), the leader's recorded identity, the group members left at leader exit (not recorded once the leader's pid was reassigned), and finish listener dispatch (a reader closed unfinished by the garbage collector skips the finish hook, which would wait on a registry lock that the collecting thread may hold; a cancelled one still finishes). | ✅ |
| stdin.py | Core | ``write_background_stdin`` — raw/submit/EOF writes to live child stdin. | ✅ |
| store_sync.py | Core | Write-through helpers: spawn upsert, vault log ref, terminal state persist. | ✅ |
| poll.py | Core | Read-side views: incremental poll payloads for ``bash_process_tool`` / auto-yield, detached entry snapshots (`snapshot_entry`, with the live `leftover_processes` count), `wait_for_exit`. | ✅ |
| progress.py | Core | Parses ``MYRM_PROGRESS`` / ``MYRM_CHECKPOINT`` markers, ANSI CSI cleanse, alias/numeric coercion, non-finite clamp, and heuristic build output. | ✅ |
| job_store_core.py | Core | Pure reconcile/status helpers for BSDL durable ledger; `BackgroundJobRecord` carries the registering server (`owner_pid`, `owner_start_stamp`, `None` for a row written without one). | ✅ |
| job_store.py | Core | SQLite BackgroundJobStore on Volume (metadata, finish dedupe, the server that registered each job, restart reconcile: stops the surviving group of each orphaned job leader whose server is gone, then marks the row orphaned). A ledger opened without the server columns gets them added, so a new and an existing ledger end identical. | ✅ |
| output_spill.py | Core | Incremental vault spill for long background stdout/stderr. | ✅ |
| session_spawn_lifecycle.py | Core | Session spawn lifecycle markers (activate/clear, auto-clean when session has no running jobs). | ✅ |

## Key Dependencies

- `toolkits.code_execution.executors`
- `utils.os_compat` — signalling the process group a job leader started
- `utils.process_start` — a process's start time that a system clock step does not move (the identity of the leader and of each group member)
- `utils.db.sqlite` — connection hardening for the job ledger
- `psutil` (core dependency) — reading a job's process group and each member's start time
