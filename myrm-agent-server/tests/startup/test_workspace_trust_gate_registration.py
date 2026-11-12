"""Importing the HTTP application registers the MCP spawn gate, whichever route groups are loaded.

[INPUT]
- app.main::app (POS: 应用入口；导入即向 MCP 传输注册工作区信任闸)
- myrm_agent_harness.toolkits.mcp.transport::get_workspace_trust_gate (POS: MCP 传输在拉起子进程前咨询的宿主信任闸)

[OUTPUT]
- Regression coverage that the gate is registered in a fresh interpreter right after the application module is imported

[POS]
Startup tests. The MCP transport spawns servers without any check while no gate is registered, and the gate is
registered by importing the harness workspace-trust package. Route groups are imported on demand, so no router's import
chain can be relied on to bring that package in: the application module imports it itself.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_RESULT_FILE_ENV = "MYRM_TRUST_GATE_RESULT_FILE"

_PROBE_SOURCE = f"""
import json
import os
from pathlib import Path

import app.main  # noqa: F401
from myrm_agent_harness.toolkits.mcp.transport import get_workspace_trust_gate

Path(os.environ[{_RESULT_FILE_ENV!r}]).write_text(json.dumps(dict(registered=get_workspace_trust_gate() is not None)))
"""


def test_importing_the_application_registers_the_mcp_spawn_gate(tmp_path: Path) -> None:
    result_file = tmp_path / "result.json"
    completed = subprocess.run(
        [sys.executable, "-c", _PROBE_SOURCE],
        cwd=_SERVER_ROOT,
        env={**os.environ, _RESULT_FILE_ENV: str(result_file)},
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr[-3000:]
    assert json.loads(result_file.read_text()) == {"registered": True}
