"""Shared helpers for bash compressor live/API E2E tests."""

from __future__ import annotations

import json
import os
import sys
import uuid
from collections.abc import Callable
from pathlib import Path

import httpx
from myrm_agent_harness.agent.meta_tools.bash._compression.output_compressor import (
    compress_output,
)

from tests.api.agent.utils import get_lite_model_selection, get_model_selection

E2E_FILTERS_YAML = """filters:
  - name: e2e-filter-run
    match_command: 'run\\.sh'
    replace:
      - pattern: 'E2E_MASK_TOKEN=\\w+'
        replacement: 'E2E_MASKED_VAL'
    strip_lines_matching:
      - '^E2E_DEBUG:'
"""

_DEFAULT_BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")


def _ensure_scripts_dev_importable() -> None:
    """Put both dev-script roots on sys.path so isolated_runtime imports resolve."""
    root = Path(__file__).resolve().parents[3]
    for dev_dir in (root / "scripts" / "dev", root / "myrm-agent" / "scripts" / "dev"):
        dev_str = str(dev_dir)
        if dev_str not in sys.path:
            sys.path.insert(0, dev_str)


def _backend_runtime_data_dir(backend_url: str) -> Path | None:
    """Resolve the isolated-runtime dataDir backing ``backend_url``, if any.

    verify-api private runtimes are registered under
    ``{isolated_root}/registry.json`` keyed by backend port. Shared :8080 has no
    registry entry and returns None. Only isolated runtimes are safe to mutate
    (seed providers / read workspace), so this guard keeps shared stacks untouched.
    """
    _ensure_scripts_dev_importable()
    try:
        from isolated_runtime.allocator import isolated_root  # noqa: PLC0415
    except ImportError:
        return None
    port_raw = backend_url.rsplit(":", 1)[-1]
    if not port_raw.isdigit():
        return None
    port = int(port_raw)
    registry_path = isolated_root() / "registry.json"
    if not registry_path.is_file():
        return None
    try:
        from isolated_runtime.registry import read_registry  # noqa: PLC0415

        records = read_registry(registry_path)
    except (RuntimeError, OSError, ImportError):
        return None
    for record in records.values():
        if isinstance(record, dict) and record.get("backendPort") == port:
            data_dir = record.get("dataDir")
            return Path(data_dir) if data_dir else None
    return None


def resolve_backend_workspaces_root(backend_url: str) -> Path:
    """Workspaces root of the backend serving ``backend_url``.

    Isolated runtimes write workspaces under ``{dataDir}/harness/workspaces``;
    local/shared backends use ``resolve_workspaces_root()``. Live E2E tests must
    read the filters.yaml written by the backend process, so they resolve the
    root from the registry instead of guessing from the test-side env.
    """
    data_dir = _backend_runtime_data_dir(backend_url)
    if data_dir is not None:
        return data_dir / "harness" / "workspaces"
    return resolve_workspaces_root()


def seed_providers_from_test_env(backend_url: str) -> bool:
    """Seed .env.test model providers into an empty isolated runtime backend.

    verify-api private backends boot with an empty database (no providers), so
    model-selection probes fail until providers are seeded. This is idempotent:
    it only writes when the backend has no default base model, and only touches
    backends registered in the isolated runtime registry (never shared :8080).
    """
    data_dir = _backend_runtime_data_dir(backend_url)
    if data_dir is None:
        return False
    try:
        from tests.support.test_secrets import resolve_test_env  # noqa: PLC0415
    except ImportError:
        return False

    basic_model = (resolve_test_env("BASIC_MODEL") or "").strip()
    basic_key = (resolve_test_env("BASIC_API_KEY") or "").strip()
    if not basic_model or not basic_key:
        return False
    lite_model = (resolve_test_env("LITE_MODEL") or "").strip()
    lite_key = (resolve_test_env("LITE_API_KEY") or "").strip()
    lite_url = resolve_test_env("LITE_BASE_URL") or "https://api.minimaxi.com/v1"
    basic_url = resolve_test_env("BASIC_BASE_URL") or lite_url

    def _provider_id(model: str) -> str:
        if "/" in model:
            return model.split("/", 1)[0]
        return "minimax"

    def _model_id(model: str) -> str:
        return model.split("/", 1)[1] if "/" in model else model

    def _provider_type(provider_id: str) -> str:
        normalized = provider_id.replace("-", "_")
        if normalized == "minimax":
            return "minimax"
        if normalized in {"openai", "openai_like", "openai_compatible"}:
            return "openai"
        return normalized

    def _entry(model: str, key: str, url: str) -> dict[str, object]:
        pid = _provider_id(model)
        return {
            "id": pid,
            "name": "MiniMax" if pid == "minimax" else pid,
            "routingProfile": pid,
            "isBuiltIn": pid == "minimax",
            "isEnabled": True,
            "apiUrl": url.rstrip("/"),
            "apiKeys": [{"key": key, "isActive": True}],
            "enabledModels": [_model_id(model)],
            "availableModels": [_model_id(model)],
            "providerType": _provider_type(pid),
        }

    basic_entry = _entry(basic_model, basic_key, basic_url)
    lite_entry = _entry(lite_model, lite_key, lite_url) if lite_model and lite_key else None
    base_primary = {"providerId": basic_entry["id"], "model": basic_entry["enabledModels"][0]}
    payload = {
        "deviceId": "e2e-bash-compressor",
        "value": {
            "providers": [basic_entry] if lite_entry is None else [basic_entry, lite_entry],
            "defaultModelConfig": {
                "baseModel": {
                    "primary": base_primary,
                    "fallback": None,
                    "temperature": 0.7,
                    "modelKwargs": {},
                },
                "liteModel": (
                    {
                        "primary": {
                            "providerId": lite_entry["id"],
                            "model": lite_entry["enabledModels"][0],
                        },
                        "fallback": None,
                    }
                    if lite_entry is not None
                    else None
                ),
                "fastModeModel": None,
                "routingConfig": None,
                "visionFallbackModel": None,
            },
            "customModelInfo": {},
        },
    }
    try:
        with httpx.Client(base_url=backend_url, timeout=30.0) as client:
            resp = client.get("/api/v1/config/providers", timeout=15.0)
            if resp.status_code == 200:
                try:
                    body = resp.json()
                except ValueError:
                    body = {}
                value = body.get("value") if isinstance(body, dict) else body
                primary = None
                if isinstance(value, dict):
                    primary = value.get("defaultModelConfig", {}).get("baseModel", {}).get("primary")
                if isinstance(primary, dict) and primary.get("providerId") and primary.get("model"):
                    return True
            put = client.put("/api/v1/config/providers", json=payload, timeout=30.0)
            return put.status_code == 200
    except (httpx.HTTPError, OSError):
        return False


def _probe_with_seed_fallback(
    selection_getter: Callable[[], dict[str, object]],
    backend_url: str,
) -> dict[str, object] | None:
    """Probe a model selection; when the private backend has no providers, seed and retry."""
    try:
        selection = selection_getter()
    except Exception:
        return None
    if _probe_model_selection_works(selection, backend_url=backend_url):
        return selection
    if seed_providers_from_test_env(backend_url):
        try:
            selection = selection_getter()
        except Exception:
            return None
        if _probe_model_selection_works(selection, backend_url=backend_url):
            return selection
    return None


def _probe_model_selection_works(
    selection: dict[str, object],
    *,
    backend_url: str = _DEFAULT_BACKEND_URL,
) -> bool:
    """Return True when agent-stream accepts the model selection."""
    payload = {
        "messageId": f"probe-{uuid.uuid4().hex[:8]}",
        "query": "Reply with exactly: PROBE_OK",
        "modelSelection": selection,
        "actionMode": "agent",
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    try:
        with httpx.Client(base_url=backend_url, timeout=90.0) as client:
            with client.stream(
                "POST",
                "/api/v1/agents/agent-stream",
                json=payload,
                timeout=90.0,
            ) as resp:
                if resp.status_code != 200:
                    return False
                for line in resp.iter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[6:])
                    except json.JSONDecodeError:
                        continue
                    if not event:
                        continue
                    event_type = event.get("type")
                    if event_type == "error":
                        err = str(event.get("error", ""))
                        if any(
                            token in err
                            for token in (
                                "Invalid API Key",
                                "401",
                                "Authentication",
                                "auth_permanent",
                            )
                        ):
                            return False
                    if event_type in ("message", "reasoning", "tool_stdout_chunk"):
                        data = event.get("data")
                        if data:
                            return True
                    if event_type == "message_end":
                        return True
    except Exception:
        return False
    return False


def resolve_working_base_selection(
    *,
    backend_url: str = _DEFAULT_BACKEND_URL,
) -> dict[str, object]:
    """Pick BASIC or LITE model selection that passes a live auth probe.

    Private verify-api backends boot with an empty provider DB; when the initial
    probe fails, providers are seeded from ``.env.test`` (idempotent) and the
    probe is retried once before giving up.
    """
    for _label, getter in (
        ("BASIC", get_model_selection),
        ("LITE", get_lite_model_selection),
    ):
        selected = _probe_with_seed_fallback(getter, backend_url)
        if selected is not None:
            return selected
    raise RuntimeError("No working model API key in .env.test (probed BASIC_MODEL and LITE_MODEL)")


def apply_workspace_compression(
    chat_id: str,
    raw_stdout: str,
    *,
    workspaces_root: Path | None = None,
) -> str:
    """Replay declarative compression on raw bash stdout (tool_stdout_chunk is pre-compression)."""
    if not raw_stdout.strip():
        return raw_stdout
    ws = _resolve_workspace_root(chat_id, workspaces_root=workspaces_root)
    if not (ws / ".myrm/filters.yaml").exists():
        return raw_stdout
    for cmd in ("bash run.sh", "bash ./run.sh", "run.sh"):
        compressed = compress_output(cmd, raw_stdout, workspace_root=str(ws))
        if compressed != raw_stdout:
            return compressed
    return raw_stdout


def resolve_workspaces_root() -> Path:
    """Resolve the harness workspaces root the same way the agent runtime does.

    Harness workspaces live under ``{state_dir}/harness/workspaces`` where
    ``state_dir`` comes from ``MYRM_DATA_DIR`` (tests) or ``~/.myrm`` (default).
    Hard-coding ``~/.myrm`` would silently miss the isolated test workspace.
    """
    state_dir = os.environ.get("MYRM_DATA_DIR", "").strip()
    base = Path(state_dir).expanduser().resolve() if state_dir else Path.home() / ".myrm"
    return base / "harness" / "workspaces"


def _resolve_workspace_root(
    chat_id: str,
    *,
    workspaces_root: Path | None = None,
) -> Path:
    """Resolve the chat workspace root (``{workspaces_root}/chat_{chat_id}``)."""
    root = workspaces_root or resolve_workspaces_root()
    return root / f"chat_{chat_id}"
