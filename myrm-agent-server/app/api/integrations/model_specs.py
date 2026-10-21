"""Ollama hardware cookbook model specifications.

[INPUT]
- myrm-agent-server/assets/cookbook_specs.json (POS: 产品资产目录中的 bundled 规格表)

[OUTPUT]
- get_dynamic_model_specs: 带缓存的 bundled 模型规格列表

[POS]
Settings Hardware Cookbook 使用的 Ollama 模型规格数据源。
"""

from __future__ import annotations

import asyncio
import json
import time
from pathlib import Path

_CACHE: tuple[float, list[dict[str, object]]] | None = None
_LOCK = asyncio.Lock()


def _bundled_specs_path() -> Path:
    server_root = Path(__file__).resolve().parents[3]
    return server_root / "assets" / "cookbook_specs.json"


def _load_bundled_specs() -> list[dict[str, object]]:
    path = _bundled_specs_path()
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        msg = "cookbook_specs.json must contain a JSON array"
        raise TypeError(msg)
    return raw


async def get_dynamic_model_specs() -> list[dict[str, object]]:
    """Return cached model specs from bundled assets."""
    global _CACHE
    now = time.monotonic()

    if _CACHE and (now - _CACHE[0]) < 3600.0:
        return _CACHE[1]

    async with _LOCK:
        if _CACHE and (now - _CACHE[0]) < 3600.0:
            return _CACHE[1]

        specs = _load_bundled_specs()
        _CACHE = (now, specs)
        return specs
