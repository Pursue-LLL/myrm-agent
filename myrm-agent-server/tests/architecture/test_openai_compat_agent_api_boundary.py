"""Architecture gate: /v1 OpenAI-compatible surface is Agent API only (no LLM gateway)."""

from __future__ import annotations

from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parents[2]
MONOREPO_ROOT = SERVER_ROOT.parents[1]
HARNESS_ROUTING = (
    MONOREPO_ROOT
    / "myrm-agent-harness"
    / "src"
    / "myrm_agent_harness"
    / "toolkits"
    / "llms"
    / "routing"
)
FRONTEND_INTEGRATION = (
    MONOREPO_ROOT
    / "myrm-agent"
    / "myrm-agent-frontend"
    / "src"
    / "components"
    / "features"
    / "settings"
    / "sections"
)

OPENAI_COMPAT_ALLOWED = frozenset(
    {
        "__init__.py",
        "_ARCH.md",
        "auth.py",
        "completions.py",
        "models.py",
        "router.py",
        "types.py",
    }
)

REMOVED_GATEWAY_PATHS = (
    SERVER_ROOT / "app" / "api" / "openai_compat" / "passthrough.py",
    SERVER_ROOT / "app" / "api" / "openai_compat" / "vision_bridge.py",
    FRONTEND_INTEGRATION / "system" / "ProxySettingsCard.tsx",
    FRONTEND_INTEGRATION / "integration" / "ComboEditorCard.tsx",
    FRONTEND_INTEGRATION / "integration" / "CliConfigTemplates.tsx",
    HARNESS_ROUTING / "combo",
)


def test_openai_compat_module_is_agent_api_only() -> None:
    compat_dir = SERVER_ROOT / "app" / "api" / "openai_compat"
    assert compat_dir.is_dir()
    assert frozenset(p.name for p in compat_dir.iterdir() if p.is_file()) == OPENAI_COMPAT_ALLOWED


def test_llm_gateway_modules_must_not_return() -> None:
    for path in REMOVED_GATEWAY_PATHS:
        assert not path.exists(), f"removed LLM gateway path must not exist: {path}"
