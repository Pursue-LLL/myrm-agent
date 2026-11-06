"""Lazy agent-runtime startup.

[INPUT]
- app.main (POS: HTTP application import surface)
- app.ai_agents.general_agent.tools::ensure_tool_layer_bootstrap (POS: lazy tool registration)

[OUTPUT]
- Regression coverage for keeping provider SDKs, the tokenizer stack and the server tool
  bootstrap out of the HTTP-server import path.

[POS]
Startup tests. The model transport speaks HTTP through httpx and loads no provider SDK, so
the server must become healthy without any of those SDKs (or the tokenizer stack) and
without registering tool layers eagerly; a future eager import would silently add seconds
to every launch.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

from app.ai_agents.general_agent.tools import ensure_tool_layer_bootstrap

_SERVER_ROOT = Path(__file__).resolve().parents[2]
# Heavy third-party stacks a model call may need later but the HTTP import path must not pay for.
_DEFERRED_MODULES = ("openai", "anthropic", "boto3", "google.genai", "tiktoken", "tokenizers")


def test_importing_app_main_keeps_heavy_agent_runtime_lazy() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.main; "
            f"print(sorted(m for m in {_DEFERRED_MODULES!r} if m in sys.modules)); "
            "print('app.ai_agents.general_agent.tools._tool_layer_bootstrap' in sys.modules)",
        ],
        cwd=_SERVER_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    deferred_loaded, bootstrap_loaded = result.stdout.strip().splitlines()
    assert deferred_loaded == "[]", result.stderr
    assert bootstrap_loaded == "False", result.stderr


def test_tool_layer_bootstrap_is_idempotent() -> None:
    import app.ai_agents.general_agent.tools as tools_package

    ensure_tool_layer_bootstrap()
    ensure_tool_layer_bootstrap()

    assert tools_package._bootstrapped is True


@pytest.mark.asyncio
async def test_startup_preload_calls_the_tool_layer_bootstrap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.server import lifespan

    calls: list[bool] = []
    monkeypatch.setattr(
        "app.ai_agents.general_agent.tools.ensure_tool_layer_bootstrap",
        lambda: calls.append(True),
    )

    await lifespan._preload_agent_tool_layers()

    assert calls == [True]
