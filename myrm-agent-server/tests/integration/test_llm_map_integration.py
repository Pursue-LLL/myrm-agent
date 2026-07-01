"""llm_map integration — full chain, no mock on key paths.

Covers: profile flag wiring, real lite-LLM tool invoke, and prebuilt template seed.
HTTP template listing/instantiate lives in test_agent_templates_api.py.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml
from langchain_openai import ChatOpenAI

from app.ai_agents.agents import AgentFactory, GeneralAgentParams
from app.core.types import ModelConfig
from app.services.agent.profile_resolver import resolve_builtin_tool_flags
from myrm_agent_harness.agent.meta_tools.llm_map.llm_map_tool import TOOL_NAME, create_llm_map_tool
from tests.support.test_secrets import load_test_secrets

_SERVER_ROOT = Path(__file__).resolve().parents[2]
_BATCH_TEMPLATE = _SERVER_ROOT / "assets" / "prebuilt_agents" / "batch_processing_assistant.yaml"


def _build_lite_llm() -> ChatOpenAI:
    secrets = load_test_secrets()
    if not secrets.has_lite_credentials:
        pytest.skip("LITE_MODEL / LITE_API_KEY (or BASIC fallbacks) required in .env.test")
    raw_model = secrets.lite_model or secrets.basic_model
    api_key = secrets.lite_api_key or secrets.basic_api_key
    base_url = secrets.lite_base_url or secrets.basic_base_url or None
    model = raw_model.split("/", 1)[1] if "/" in raw_model else raw_model
    return ChatOpenAI(model=model, api_key=api_key, base_url=base_url, temperature=0)


class TestLlmMapProfileWiring:
    """Server profile → harness flag mapping (no LLM)."""

    def test_llm_map_in_tools_sets_enable_flag(self) -> None:
        flags = resolve_builtin_tool_flags(["llm_map", "answer_tool"])
        assert flags["enable_llm_map"] is True

    def test_default_tools_disable_llm_map(self) -> None:
        flags = resolve_builtin_tool_flags(["web_search", "memory"])
        assert flags["enable_llm_map"] is False

    def test_default_enabled_builtin_tools_excludes_llm_map(self) -> None:
        from app.services.agent.profile_resolver import DEFAULT_ENABLED_BUILTIN_TOOLS

        flags = resolve_builtin_tool_flags(DEFAULT_ENABLED_BUILTIN_TOOLS)
        assert "llm_map" not in DEFAULT_ENABLED_BUILTIN_TOOLS
        assert flags["enable_llm_map"] is False

    def test_llm_map_tool_is_extended_layer(self) -> None:
        from myrm_agent_harness.agent.tool_management.tool_layers import ToolLayer, get_tool_layer

        assert get_tool_layer("llm_map_tool") == ToolLayer.EXTENDED

    def test_factory_passes_enable_llm_map_to_general_agent(self) -> None:
        params = GeneralAgentParams(
            query="batch",
            model_cfg=ModelConfig(model="test/model", api_key="test-key"),
            enable_llm_map=True,
        )
        agent = AgentFactory.create_general_agent(params)
        assert agent.enable_llm_map is True


class TestBatchProcessingTemplateSeed:
    """Prebuilt YAML seed integrity (filesystem, no HTTP)."""

    def test_batch_processing_assistant_seed_exists(self) -> None:
        assert _BATCH_TEMPLATE.is_file(), f"missing seed: {_BATCH_TEMPLATE}"

    def test_seed_enables_llm_map_and_documents_cap(self) -> None:
        data = yaml.safe_load(_BATCH_TEMPLATE.read_text(encoding="utf-8"))
        assert data is not None
        tools: list[str] = data.get("enabled_builtin_tools") or []
        assert "llm_map" in tools
        prompt = data.get("system_prompt") or ""
        assert "llm_map_tool" in prompt
        assert "200" in prompt


class TestLlmMapFrontendLocales:
    """Frontend i18n for builtin tool panel (read locale JSON from disk)."""

    _FRONTEND_ROOT = _SERVER_ROOT.parent / "myrm-agent-frontend" / "locales"

    def test_en_and_zh_builtin_tool_descs_mention_200_cap(self) -> None:
        import json as json_mod

        for locale in ("en.json", "zh.json"):
            path = self._FRONTEND_ROOT / locale
            assert path.is_file(), f"missing {path}"
            data = json_mod.loads(path.read_text(encoding="utf-8"))
            desc = data["agent"]["configPanel"]["builtinToolDescs"]["llm_map"]
            assert "200" in desc, f"{locale} llm_map desc must mention 200-item cap"


class TestLlmMapVaultSpillIntegration:
    """Real ArtifactVault spill (no mock on vault I/O)."""

    def test_spill_results_writes_vault_pointer(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import myrm_agent_harness.agent.meta_tools.llm_map.llm_map_tool as mod

        monkeypatch.setattr(mod, "_resolve_workspace_root", lambda: str(tmp_path))
        serialised = [{"index": i, "status": "ok", "output": f"row-{i}"} for i in range(5)]
        pointer = mod._spill_results(serialised)
        assert pointer is not None
        assert pointer.startswith("vault://")

        from myrm_agent_harness.agent.artifacts.vault import ArtifactVault

        content = ArtifactVault(str(tmp_path)).get(pointer).decode("utf-8")
        assert "row-0" in content


@pytest.mark.asyncio
class TestLlmMapToolRealLlmInvoke:
    """Real lite LLM → create_llm_map_tool → engine fan-out (no mocks)."""

    @pytest.mark.skipif(
        not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
        reason="Requires LITE_API_KEY or BASIC_API_KEY in .env.test",
    )
    async def test_three_item_fan_out_succeeds(self) -> None:
        llm = _build_lite_llm()
        tool = create_llm_map_tool(llm, fallback_llm=llm, max_items=10)
        assert tool.name == TOOL_NAME

        result = await tool.ainvoke(
            {
                "instruction": (
                    "Reply with exactly one word: POSITIVE if the text expresses praise, "
                    "NEGATIVE if criticism, NEUTRAL otherwise."
                ),
                "items": [
                    "This product is amazing and I love it.",
                    "Terrible experience, would not buy again.",
                    "The box arrived on Tuesday.",
                ],
                "max_concurrency": 2,
            }
        )
        assert result["success"] is True
        summary = result["summary"]
        assert isinstance(summary, dict)
        assert summary["total"] == 3
        assert summary["succeeded"] == 3
        assert summary["failed"] == 0
        preview = result.get("preview")
        assert isinstance(preview, list)
        assert len(preview) == 3

    @pytest.mark.skipif(
        not os.environ.get("LITE_API_KEY") and not os.environ.get("BASIC_API_KEY"),
        reason="Requires LITE_API_KEY or BASIC_API_KEY in .env.test",
    )
    async def test_over_cap_rejected_without_llm_calls(self) -> None:
        llm = _build_lite_llm()
        tool = create_llm_map_tool(llm, max_items=2)
        result = await tool.ainvoke(
            {
                "instruction": "Summarise in one word.",
                "items": ["a", "b", "c"],
            }
        )
        assert result["success"] is False
        assert result["max_items"] == 2
        assert result["received_items"] == 3
        assert "Split into batches" in str(result.get("error", ""))
