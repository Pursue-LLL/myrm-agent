"""自定义模型单价登记与缓存单价解析单元测试.

[INPUT]
- myrm_agent_harness.toolkits.llms.catalog::model_info
- app.core.channel_bridge.model_resolver::register_custom_model_pricing

[OUTPUT]
- 验证 register_custom_model_pricing 正确推断 provider 前缀（非固定 "custom"）
- 验证 cache_read_input_token_cost 精确换算
- 验证限定名与裸模型名双向注册到模型目录

[POS]
tests/core/channel_bridge/test_model_resolver_pricing_repair.py 镜像单元测试。
"""

import pytest
from myrm_agent_harness.toolkits.llms.catalog import model_info, store

from app.core.channel_bridge.model_resolver import register_custom_model_pricing


@pytest.fixture(autouse=True)
def _isolated_catalog_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registrations a test makes never outlive it."""
    monkeypatch.setattr(store, "_REGISTERED", {})


def test_register_custom_model_pricing_with_provider_inference_and_cache() -> None:
    """测试自定义模型单价登记前缀推断、缓存单价与双向映射."""
    providers_dict = {
        "providers": [
            {
                "id": "custom_openai_service",
                "providerType": "openai-like",
            }
        ],
        "customModelInfo": {
            "custom_openai_service/mimo-v2.5-pro": {
                "input_cost_per_million": 1.5,
                "output_cost_per_million": 4.5,
                "cache_read_cost_per_million": 0.5,
                "max_input_tokens": 64000,
            },
            "custom_openai_service/deepseek-custom-v3": {
                "input_cost_per_million": 2.0,
                "output_cost_per_million": 8.0,
                # 无显式缓存读取单价
            },
        },
    }

    registered_count = register_custom_model_pricing(providers_dict)
    assert registered_count == 2

    # 1. 验证 mimo-v2.5-pro 的限定名与裸名注册
    # _to_route_model_id 会将 custom_openai_service + mimo-v2.5-pro 转换为 openai/mimo-v2.5-pro
    qualified_key = "openai/mimo-v2.5-pro"
    bare_key = "mimo-v2.5-pro"

    entry_qual = model_info(qualified_key)
    assert entry_qual is not None
    assert entry_qual["input_cost_per_token"] == pytest.approx(1.5 / 1_000_000)
    assert entry_qual["output_cost_per_token"] == pytest.approx(4.5 / 1_000_000)
    assert entry_qual["cache_read_input_token_cost"] == pytest.approx(0.5 / 1_000_000)
    assert entry_qual["provider"] == "openai"  # 不再是死板的 "custom"

    # 裸名双向注册验证
    entry_bare = model_info(bare_key)
    assert entry_bare is not None
    assert entry_bare["input_cost_per_token"] == pytest.approx(1.5 / 1_000_000)
    assert entry_bare["provider"] == "openai"

    # 2. 验证无显式缓存单价时不会产生虚假负数
    entry_ds = model_info("openai/deepseek-custom-v3")
    assert entry_ds is not None
    assert "cache_read_input_token_cost" not in entry_ds


def test_register_custom_model_pricing_empty_or_zero() -> None:
    """测试空单价或零单价跳过注册."""
    empty_dict = {
        "providers": {
            "p1": {
                "customModels": [
                    {
                        "model": "free-model",
                        "input_cost_per_million": 0,
                        "output_cost_per_million": 0,
                    }
                ]
            }
        }
    }
    assert register_custom_model_pricing(empty_dict) == 0
