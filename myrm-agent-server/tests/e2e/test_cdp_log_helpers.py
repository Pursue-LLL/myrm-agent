"""Unit tests for Chrome E2E backend log helpers."""

from __future__ import annotations

import json
import sys
from pathlib import Path

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    backend_log_path,
    count_execution_cache_in_log,
    count_turn_prewarm_in_log,
    snapshot_backend_log_offset,
)


def test_count_turn_prewarm_in_log(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "backend.log"
    log_path.write_text(
        "noise\nTurn prewarm requested: chat_id=c1 agent_id=default\n"
        "Turn prewarm requested: chat_id=c2 agent_id=default\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_BACKEND_LOG", str(log_path))
    assert count_turn_prewarm_in_log(since_offset=0) == 2
    assert count_turn_prewarm_in_log(since_offset=log_path.stat().st_size) == 0


def test_count_execution_cache_in_log(monkeypatch, tmp_path: Path) -> None:
    log_path = tmp_path / "backend.log"
    log_path.write_text(
        "execution_cache_created scope=x\nexecution_cache_reuse scope=x\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("MYRM_BACKEND_LOG", str(log_path))
    created, reused = count_execution_cache_in_log(since_offset=0)
    assert created == 1
    assert reused == 1


def _write_isolated_registry(isolated_root: Path, *, backend_port: int, state_dir: Path) -> None:
    isolated_root.mkdir(parents=True, exist_ok=True)
    registry = {
        "schemaVersion": 5,
        "runtimes": {
            "rt-live": {
                "runtimeId": "rt-live",
                "agentRoot": str(isolated_root),
                "frontendPort": 3000,
                "backendPort": backend_port,
                "stateDir": str(state_dir),
                "dataDir": str(state_dir),
                "ownerPid": 1234,
                "ownerToken": "token",
                "heartbeatAt": 1.0,
                "phase": "running",
            }
        },
    }
    (isolated_root / "registry.json").write_text(
        json.dumps(registry), encoding="utf-8"
    )


def test_backend_log_override_wins_over_private_port(monkeypatch, tmp_path: Path) -> None:
    override = tmp_path / "override-backend.log"
    override.write_text("x\n", encoding="utf-8")
    monkeypatch.setenv("MYRM_BACKEND_LOG", str(override))
    monkeypatch.setenv("E2E_API_BASE", "http://127.0.0.1:18081")
    assert backend_log_path() == override


def test_backend_log_shared_port_uses_dev_state_dir(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("E2E_API_BASE", "http://127.0.0.1:8080")
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path))
    assert backend_log_path() == tmp_path / "backend.log"


def test_backend_log_private_port_resolves_registry_log(
    monkeypatch, tmp_path: Path
) -> None:
    isolated_root = tmp_path / "isolated"
    runtime_dir = isolated_root / "runtimes" / "rt-live" / "state"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "backend.log").write_text(
        "execution_cache_created scope=x\n", encoding="utf-8"
    )
    _write_isolated_registry(isolated_root, backend_port=18081, state_dir=runtime_dir)
    monkeypatch.setenv("MYRM_ISOLATED_ROOT", str(isolated_root))
    monkeypatch.delenv("MYRM_DEV_STATE_DIR", raising=False)
    resolved = backend_log_path(api_url="http://127.0.0.1:18081")
    assert resolved == runtime_dir / "backend.log"


def test_backend_log_private_port_missing_registry_falls_back(
    monkeypatch, tmp_path: Path
) -> None:
    isolated_root = tmp_path / "isolated-empty"
    isolated_root.mkdir(parents=True)
    monkeypatch.setenv("MYRM_ISOLATED_ROOT", str(isolated_root))
    monkeypatch.setenv("MYRM_DEV_STATE_DIR", str(tmp_path))
    resolved = backend_log_path(api_url="http://127.0.0.1:18081")
    assert resolved == tmp_path / "backend.log"


def test_count_execution_cache_in_log_private_api_url(
    monkeypatch, tmp_path: Path
) -> None:
    isolated_root = tmp_path / "isolated"
    runtime_dir = isolated_root / "runtimes" / "rt-live" / "state"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "backend.log").write_text(
        "Turn prewarm requested: chat_id=c1\n"
        "execution_cache_created scope=x\n"
        "execution_cache_reuse scope=x\n",
        encoding="utf-8",
    )
    _write_isolated_registry(isolated_root, backend_port=18081, state_dir=runtime_dir)
    monkeypatch.setenv("MYRM_ISOLATED_ROOT", str(isolated_root))
    monkeypatch.delenv("MYRM_BACKEND_LOG", raising=False)
    monkeypatch.delenv("MYRM_DEV_STATE_DIR", raising=False)
    api_url = "http://127.0.0.1:18081"
    offset = snapshot_backend_log_offset(api_url=api_url)
    assert offset == (runtime_dir / "backend.log").stat().st_size
    created, reused = count_execution_cache_in_log(since_offset=0, api_url=api_url)
    assert created == 1
    assert reused == 1
    assert count_turn_prewarm_in_log(since_offset=0, api_url=api_url) == 1
