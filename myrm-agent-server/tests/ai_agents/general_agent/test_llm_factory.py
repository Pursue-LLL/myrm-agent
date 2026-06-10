from app.ai_agents.general_agent import llm_factory
from app.ai_agents.general_agent.llm_factory import select_tool_capable_model_cfg
from app.core.types import ModelConfig


def test_select_tool_capable_model_cfg_keeps_main_when_it_supports_tools(
    monkeypatch,
) -> None:
    main_cfg = ModelConfig(model="deepseek/deepseek-chat", api_key="main-key")
    fallback_cfg = ModelConfig(model="minimax/MiniMax-M2.5", api_key="fallback-key")

    def fake_supports(model_name: str) -> bool:
        return model_name == main_cfg.model

    monkeypatch.setattr(llm_factory, "_supports_function_calling", fake_supports)

    selected_cfg, source = select_tool_capable_model_cfg(
        main_cfg,
        fallback_model_cfg=fallback_cfg,
    )

    assert selected_cfg is main_cfg
    assert source == "main"


def test_select_tool_capable_model_cfg_uses_explicit_fallback_for_tools(
    monkeypatch,
) -> None:
    main_cfg = ModelConfig(model="unknown/unknown-model", api_key="main-key")
    fallback_cfg = ModelConfig(model="minimax/MiniMax-M2.5", api_key="fallback-key")

    def fake_supports(model_name: str) -> bool:
        return model_name == fallback_cfg.model

    monkeypatch.setattr(llm_factory, "_supports_function_calling", fake_supports)

    selected_cfg, source = select_tool_capable_model_cfg(
        main_cfg,
        fallback_model_cfg=fallback_cfg,
    )

    assert selected_cfg is fallback_cfg
    assert source == "fallback"


def test_select_tool_capable_model_cfg_scans_providers_for_tool_model(
    monkeypatch,
) -> None:
    main_cfg = ModelConfig(model="unknown/unknown-model", api_key="main-key")
    providers_dict: dict[str, object] = {
        "providers": [
            {
                "id": "xiaomi",
                "isEnabled": True,
                "providerType": "xiaomi",
                "apiKeys": [{"key": "xiaomi-key", "isActive": True}],
                "enabledModels": ["some-model"],
                "apiUrl": "https://xiaomi.example/v1",
            },
            {
                "id": "minimax",
                "isEnabled": True,
                "providerType": "minimax",
                "apiKeys": [{"key": "mini-key", "isActive": True}],
                "enabledModels": ["MiniMax-M2.5"],
                "apiUrl": "https://api.minimax.example/v1",
            },
        ],
    }

    def fake_supports(model_name: str) -> bool:
        return model_name == "minimax/MiniMax-M2.5"

    monkeypatch.setattr(llm_factory, "_supports_function_calling", fake_supports)

    selected_cfg, source = select_tool_capable_model_cfg(
        main_cfg,
        providers_dict=providers_dict,
    )

    assert selected_cfg.model == "minimax/MiniMax-M2.5"
    assert selected_cfg.api_key == "mini-key"
    assert selected_cfg.base_url == "https://api.minimax.example/v1"
    assert source == "provider_scan"
