"""Ownership ledger for short-lived CDP targets created by dev preflight."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import urllib.error
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TypedDict


class TransientTarget(TypedDict):
    targetId: str
    ownerPid: int
    url: str


def _state_dir() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    return Path(override) if override else Path.home() / ".local/state/myrm-dev"


def _ledger_path() -> Path:
    return _state_dir() / "cdp-transient-targets.json"


@contextmanager
def _locked_ledger() -> Iterator[Path]:
    ledger = _ledger_path()
    ledger.parent.mkdir(parents=True, exist_ok=True)
    lock_path = ledger.with_suffix(".lock")
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield ledger
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read(path: Path) -> list[TransientTarget]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(payload, list):
        return []
    result: list[TransientTarget] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        target_id = item.get("targetId")
        owner_pid = item.get("ownerPid")
        url = item.get("url")
        if isinstance(target_id, str) and target_id and isinstance(owner_pid, int):
            result.append(
                {
                    "targetId": target_id,
                    "ownerPid": owner_pid,
                    "url": url if isinstance(url, str) else "",
                }
            )
    return result


def _write(path: Path, records: list[TransientTarget]) -> None:
    if not records:
        path.unlink(missing_ok=True)
        return
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(records, separators=(",", ":")) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def register_target(target_id: str, url: str, *, owner_pid: int | None = None) -> None:
    target = target_id.strip()
    if not target:
        raise ValueError("target_id is required")
    pid = owner_pid if owner_pid is not None else os.getpid()
    with _locked_ledger() as ledger:
        records = [item for item in _read(ledger) if item["targetId"] != target]
        records.append({"targetId": target, "ownerPid": pid, "url": url})
        _write(ledger, records)


def unregister_target(target_id: str) -> None:
    target = target_id.strip()
    with _locked_ledger() as ledger:
        _write(ledger, [item for item in _read(ledger) if item["targetId"] != target])


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


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


def prune_stale_targets(cdp_port: int) -> tuple[int, int]:
    with _locked_ledger() as ledger:
        records = _read(ledger)
        stale = [item for item in records if not _pid_alive(item["ownerPid"])]
        closed_ids = {
            item["targetId"]
            for item in stale
            if _close_exact_target(cdp_port, item["targetId"])
        }
        _write(ledger, [item for item in records if item["targetId"] not in closed_ids])
    return len(closed_ids), len(stale) - len(closed_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prune stale preflight-owned CDP targets.")
    parser.add_argument("--prune", action="store_true")
    parser.add_argument("--cdp-port", type=int, default=9333)
    args = parser.parse_args()
    if not args.prune:
        parser.error("--prune is required")
    closed, failed = prune_stale_targets(args.cdp_port)
    print(f"MYRM_CHROME_PRUNE_OK: closed={closed} failed={failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
