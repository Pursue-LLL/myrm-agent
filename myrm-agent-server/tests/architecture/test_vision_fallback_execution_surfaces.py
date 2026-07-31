"""Architecture guard: vision_fallback_model_cfg must be injected on all ExecutionSurfaces."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SERVER_ROOT = _REPO_ROOT

_REQUIRED_SURFACE_FILES: tuple[tuple[str, str], ...] = (
    (
        "app/core/channel_bridge/agent_executor/execute_preamble.py",
        "vision_fallback_model_cfg=vision_fallback_model_cfg",
    ),
    (
        "app/core/cron/adapters/agent_runner.py",
        "vision_fallback_model_cfg=vision_fallback_model_cfg",
    ),
    (
        "app/api/voice/agent_bridge.py",
        "vision_fallback_model_cfg=vision_fallback_model_cfg",
    ),
    (
        "app/services/kanban/task_runner.py",
        "vision_fallback_model_cfg=vision_fallback_model_cfg",
    ),
    (
        "app/services/kanban/task_runner.py",
        "vision_fallback_model_cfgs=",
    ),
)


@pytest.mark.parametrize(("relative_path", "needle"), _REQUIRED_SURFACE_FILES)
def test_execution_surface_injects_vision_fallback_cfg(
    relative_path: str,
    needle: str,
) -> None:
    source_path = _SERVER_ROOT / relative_path
    assert source_path.is_file(), f"Missing execution surface file: {relative_path}"
    content = source_path.read_text(encoding="utf-8")
    assert needle in content, (
        f"{relative_path} must inject vision_fallback_model_cfg into GeneralAgentParams"
    )


def test_ssot_extract_function_exists() -> None:
    parser_path = _SERVER_ROOT / "app/core/channel_bridge/config_parsers.py"
    content = parser_path.read_text(encoding="utf-8")
    assert "def extract_vision_fallback_model_config(" in content
    assert "def extract_vision_fallback_model_configs(" in content
    assert "def resolve_vision_fallback_chain_for_agent(" in content
