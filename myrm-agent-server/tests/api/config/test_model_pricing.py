"""[INPUT]
- app.api.config.pricing::pricing_router
- /api/v1/config/model-pricing

[OUTPUT]
- test_model_pricing_default_list
- test_model_pricing_representative_models_are_listed_and_not_deprecated
- test_model_pricing_specific_model
- test_model_pricing_gateway_route_resolves_to_the_model_behind_it
- test_model_pricing_unknown_model_graceful
- test_model_pricing_never_guesses_by_substring
- test_model_pricing_unpriced_model_is_not_shown_as_free

[POS]
tests/api/config/test_model_pricing.py — 测试四维单价矩阵与 Cache 折扣端点。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.llms.catalog import is_deprecated, model_facts, register_model, store

from app.api.config.pricing import DEFAULT_REPRESENTATIVE_MODELS
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)

_URL = "/api/v1/config/model-pricing"


@pytest.fixture(autouse=True)
def _isolated_registrations(monkeypatch: pytest.MonkeyPatch) -> None:
    """Registrations a test makes never outlive it."""
    monkeypatch.setattr(store, "_REGISTERED", {})


def _register_priced_model(name: str) -> None:
    register_model(
        name,
        {
            "provider": "vendor",
            "input_cost_per_token": 3.0 / 1_000_000,
            "output_cost_per_token": 15.0 / 1_000_000,
            "cache_read_input_token_cost": 0.3 / 1_000_000,
            "cache_creation_input_token_cost": 3.75 / 1_000_000,
            "supports_prompt_caching": True,
        },
    )


def test_model_pricing_default_list() -> None:
    """默认请求应返回常用标杆模型的四维单价字典。"""
    response = client.get(_URL)
    assert response.status_code == 200
    data = response.json()
    assert "models" in data
    models = data["models"]
    assert isinstance(models, dict)
    assert len(models) > 0

    # 验证主流模型字段结构
    for info in models.values():
        assert "model" in info
        assert "input_cost_per_mtoken" in info
        assert "output_cost_per_mtoken" in info
        assert "cache_read_cost_per_mtoken" in info
        assert "cache_write_cost_per_mtoken" in info
        assert "supports_prompt_caching" in info
        assert isinstance(info["input_cost_per_mtoken"], (int, float))
        assert isinstance(info["output_cost_per_mtoken"], (int, float))


def test_model_pricing_representative_models_are_listed_and_not_deprecated() -> None:
    """标杆清单里每个模型都必须能在目录中解析出标价，且未过弃用日期（清单过期会在这里报警）。"""
    models = client.get(_URL).json()["models"]
    assert set(models) == set(DEFAULT_REPRESENTATIVE_MODELS)
    for name in DEFAULT_REPRESENTATIVE_MODELS:
        assert not is_deprecated(model_facts(name) or {}), f"{name} is past its deprecation date"
        assert models[name]["input_cost_per_mtoken"] > 0


def test_model_pricing_specific_model() -> None:
    """查询指定模型应准确返回该模型的四维单价与 Cache 支持情况。"""
    _register_priced_model("vendor/priced-model")
    response = client.get(f"{_URL}?model=vendor/priced-model")
    assert response.status_code == 200
    data = response.json()
    assert "vendor/priced-model" in data["models"]
    priced = data["models"]["vendor/priced-model"]

    assert priced["input_cost_per_mtoken"] == 3.0  # $3 / 1M
    assert priced["output_cost_per_mtoken"] == 15.0  # $15 / 1M
    assert priced["cache_read_cost_per_mtoken"] == 0.3  # $0.3 / 1M (90% discount)
    assert priced["cache_write_cost_per_mtoken"] == 3.75  # $3.75 / 1M (1.25x)
    assert priced["cache_read_discount"] == 0.9
    assert priced["supports_prompt_caching"] is True


def test_model_pricing_gateway_route_resolves_to_the_model_behind_it() -> None:
    """前端传入的是 provider/model 选择键：网关复合名应落到其背后模型的标价，结果仍以请求名为键。"""
    _register_priced_model("routed-priced-model")
    models = client.get(f"{_URL}?model=my-gateway/routed-priced-model").json()["models"]
    assert list(models) == ["my-gateway/routed-priced-model"]
    assert models["my-gateway/routed-priced-model"]["input_cost_per_mtoken"] == 3.0


def test_model_pricing_unknown_model_graceful() -> None:
    """查询未知模型应优雅返回空字典，不应崩溃。"""
    response = client.get(f"{_URL}?model=some-unknown-custom-model-999")
    assert response.status_code == 200
    data = response.json()
    assert data["models"] == {}


def test_model_pricing_never_guesses_by_substring() -> None:
    """只是某个目录键的子串不算命中：猜错的单价比没有单价更糟。"""
    _register_priced_model("vendor/long-model-name-x")
    assert client.get(f"{_URL}?model=long-model-name").json()["models"] == {}


def test_model_pricing_unpriced_model_is_not_shown_as_free() -> None:
    """目录收录但没有标价的模型不返回条目，避免把 $0.00 误读成免费。"""
    register_model("vendor/unpriced-model", {"provider": "vendor", "max_input_tokens": 8192})
    assert client.get(f"{_URL}?model=vendor/unpriced-model").json()["models"] == {}
