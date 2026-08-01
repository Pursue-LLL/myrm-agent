"""Host Resource Governor slot calibration benchmark (P1 dry-run SSOT)."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from typing import TypedDict

from host_resource_governor import (
    MAX_BROWSER_SLOTS,
    MIN_BROWSER_SLOTS,
    collect_host_pressure_snapshot,
    host_resource_governor_snapshot,
    reset_governor_for_tests,
    tick_governor,
)


class SlotCalibrationRow(TypedDict):
    forced_slots: int
    effective_browser_slots: int
    load_avg_1m: float
    memory_available_bytes: int
    memory_pressure: str


def run_slot_calibration_benchmark(*, now: float | None = None) -> dict[str, object]:
    """Record governor snapshot at forced 1–4 slots for sweet-spot calibration."""
    captured_at = time.time() if now is None else now
    pressure = collect_host_pressure_snapshot(now=captured_at)
    rows: list[SlotCalibrationRow] = []
    previous_override = os.environ.get("MYRM_EFFECTIVE_BROWSER_SLOTS", "")
    try:
        for forced in range(MIN_BROWSER_SLOTS, MAX_BROWSER_SLOTS + 1):
            os.environ["MYRM_EFFECTIVE_BROWSER_SLOTS"] = str(forced)
            reset_governor_for_tests(slots=forced)
            snapshot = host_resource_governor_snapshot(now=captured_at)
            rows.append(
                SlotCalibrationRow(
                    forced_slots=forced,
                    effective_browser_slots=int(snapshot["effective_browser_slots"]),
                    load_avg_1m=float(
                        snapshot.get("load_avg_1m", pressure.load_avg_1m)
                    ),
                    memory_available_bytes=int(
                        snapshot.get(
                            "memory_available_bytes",
                            pressure.memory_available_bytes,
                        )
                    ),
                    memory_pressure=str(snapshot.get("memory_pressure", "unknown")),
                )
            )
    finally:
        if previous_override:
            os.environ["MYRM_EFFECTIVE_BROWSER_SLOTS"] = previous_override
        else:
            os.environ.pop("MYRM_EFFECTIVE_BROWSER_SLOTS", None)
        reset_governor_for_tests()

    os.environ.pop("MYRM_EFFECTIVE_BROWSER_SLOTS", None)
    reset_governor_for_tests()
    recommended = tick_governor(now=captured_at)
    load_ratio = pressure.load_avg_1m / max(1, pressure.cpu_count)
    return {
        "schema_version": 1,
        "captured_at": captured_at,
        "pressure": {
            "load_avg_1m": pressure.load_avg_1m,
            "load_avg_5m": pressure.load_avg_5m,
            "cpu_count": pressure.cpu_count,
            "memory_available_bytes": pressure.memory_available_bytes,
            "load_ratio": load_ratio,
        },
        "slot_calibration": rows,
        "recommended_effective_slots": recommended,
    }


def default_output_path() -> Path:
    override = os.getenv("MYRM_DEV_STATE_DIR", "").strip()
    base = Path(override) if override else Path.home() / ".local/state/myrm-dev"
    return base / "host-governor-benchmark.json"


def write_benchmark_report(
    payload: dict[str, object],
    *,
    output_path: Path | None = None,
) -> Path:
    target = (output_path or default_output_path()).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        default="",
        help="Benchmark JSON output path (default: ~/.local/state/myrm-dev/host-governor-benchmark.json)",
    )
    args = parser.parse_args(argv)
    payload = run_slot_calibration_benchmark()
    output = write_benchmark_report(
        payload,
        output_path=Path(args.output) if args.output.strip() else None,
    )
    print(
        json.dumps(
            {
                "ok": True,
                "output_path": str(output),
                "recommended_effective_slots": payload["recommended_effective_slots"],
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
