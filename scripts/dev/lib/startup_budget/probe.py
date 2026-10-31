"""Child process of the startup budget gate: one cold measurement of the real backend.

[INPUT]
  Runs under the backend venv interpreter with PYTHONPATH=<myrm-agent-server>. The environment
  must carry MYRM_DATA_DIR (an isolated directory; the probe refuses ~/.myrm). Optional
  ``--stub MODULE`` replaces a module by a permissive stand-in before ``app.main`` is imported
  (import-only measurement: gateway_cpu_sec is null because the stubbed app cannot start).
  Backend modules (imported inside the measurement):
  app.main::app (POS: FastAPI application entry; its cold import is what gets priced);
  app.core.channel_bridge.setup::start_channel_gateway / stop_channel_gateway (POS: thin
  lifecycle layer of the IM channel gateway; its start-up is timed);
  app.database.connection::init_database (POS: database initialisation on the empty data
  directory); app.platform_utils.persistent_root::configure_persistent_root_for_local_dev
  (POS: startup-time persistent root selector); app.config.settings::settings (POS: unified
  configuration centre).

[OUTPUT]
  One ``STARTUP_BUDGET_SAMPLE {json}`` line on stdout: import_cpu_sec, modules, peak_rss_mb,
  gateway_cpu_sec. Exit 0 on success, 1 when the backend itself failed to import or start,
  2 on unsafe invocation.

[POS]
  The only code that imports the backend. CPU is ``time.process_time`` (wall time is inflated
  several-fold when the machine is oversubscribed, so it says nothing about the code).
  ``--stub`` exists so a lazy-load idea can be priced on the FULL app: importing one package in
  isolation charges it for dependencies the rest of the app shares anyway.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import resource
import sys
import time
import types
from collections.abc import Sequence
from pathlib import Path

SAMPLE_PREFIX = "STARTUP_BUDGET_SAMPLE"
_EXIT_BACKEND_FAILED = 1
_EXIT_UNSAFE = 2
# ru_maxrss is bytes on macOS and KiB on Linux.
_RSS_UNIT_BYTES = 1 if sys.platform == "darwin" else 1024


def _dummy_class(attr: str) -> type:
    return type(attr, (), {})


def install_stub(name: str) -> None:
    """Register ``name`` as a module whose every attribute is a fresh dummy class."""
    stub = types.ModuleType(name)
    # PEP 562 module-level __getattr__: `from <name> import Anything` succeeds.
    stub.__dict__["__getattr__"] = _dummy_class
    sys.modules[name] = stub


def _peak_rss_mb() -> float:
    peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return peak * _RSS_UNIT_BYTES / (1024 * 1024)


async def _gateway_startup_cpu() -> float:
    """CPU of ``start_channel_gateway()`` alone, after the database exists."""
    from app.config.settings import settings
    from app.core.channel_bridge.setup import (
        start_channel_gateway,
        stop_channel_gateway,
    )
    from app.database.connection import init_database
    from app.platform_utils.persistent_root import (
        configure_persistent_root_for_local_dev,
    )

    configure_persistent_root_for_local_dev(settings.database.state_dir)
    await init_database()
    started = time.process_time()
    await start_channel_gateway()
    elapsed = time.process_time() - started
    await stop_channel_gateway()
    return elapsed


def _unsafe_reason() -> str | None:
    data_dir = os.environ.get("MYRM_DATA_DIR")
    if not data_dir:
        return "MYRM_DATA_DIR must point to an isolated directory"
    if Path(data_dir).expanduser().resolve() == (Path.home() / ".myrm").resolve():
        return "refusing to run against the real ~/.myrm data directory"
    return None


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="startup_budget.probe")
    parser.add_argument("--stub", action="append", default=[], metavar="MODULE")
    args = parser.parse_args(argv)

    reason = _unsafe_reason()
    if reason:
        print(reason, file=sys.stderr)
        return _EXIT_UNSAFE
    os.environ.setdefault("DEPLOY_MODE", "local")
    for name in args.stub:
        install_stub(name)

    try:
        started = time.process_time()
        import app.main  # noqa: F401

        import_cpu = time.process_time() - started
        modules = len(sys.modules)
        # A stubbed app is incomplete; starting the gateway on it would fail for the wrong reason.
        gateway_cpu = None if args.stub else asyncio.run(_gateway_startup_cpu())
    except Exception as exc:  # noqa: BLE001 - process boundary: one line for the orchestrator
        print(f"backend failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return _EXIT_BACKEND_FAILED

    sample = {
        "import_cpu_sec": round(import_cpu, 3),
        "modules": modules,
        "peak_rss_mb": round(_peak_rss_mb(), 1),
        "gateway_cpu_sec": None if gateway_cpu is None else round(gateway_cpu, 3),
    }
    print(f"{SAMPLE_PREFIX} {json.dumps(sample)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
