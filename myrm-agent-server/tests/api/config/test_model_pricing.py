"""[INPUT]
- app.api.config.pricing::pricing_router
- /api/v1/config/model-pricing

[OUTPUT]
- test_model_pricing_default_list
- test_model_pricing_specific_model
- test_model_pricing_unknown_model_graceful

[POS]
tests/api/config/test_model_pricing.py — 测试四维单价矩阵与 Cache 折扣端点。
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="config")
client = TestClient(app)

_URL = "/api/v1/config/model-pricing"


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
    for model_name, info in models.items():
        assert "model" in info
        assert "input_cost_per_mtoken" in info
        assert "output_cost_per_mtoken" in info
        assert "cache_read_cost_per_mtoken" in info
        assert "cache_write_cost_per_mtoken" in info
        assert "supports_prompt_caching" in info
        assert isinstance(info["input_cost_per_mtoken"], (int, float))
        assert isinstance(info["output_cost_per_mtoken"], (int, float))


def test_model_pricing_specific_model() -> None:
    """查询指定模型应准确返回该模型的四维单价与 Cache 支持情况。"""
    response = client.get(f"{_URL}?model=claude-3-5-sonnet-20241022")
    assert response.status_code == 200
    data = response.json()
    assert "claude-3-5-sonnet-20241022" in data["models"]
    sonnet = data["models"]["claude-3-5-sonnet-20241022"]

    assert sonnet["input_cost_per_mtoken"] == 3.0  # $3 / 1M
    assert sonnet["output_cost_per_mtoken"] == 15.0  # $15 / 1M
    assert sonnet["cache_read_cost_per_mtoken"] == 0.3  # $0.3 / 1M (90% discount)
    assert sonnet["cache_write_cost_per_mtoken"] == 3.75  # $3.75 / 1M (1.25x)
    assert sonnet["cache_read_discount"] == 0.9
    assert sonnet["supports_prompt_caching"] is True


def test_model_pricing_unknown_model_graceful() -> None:
    """查询未知模型应优雅返回空字典，不应崩溃。"""
    response = client.get(f"{_URL}?model=some-unknown-custom-model-999")
    assert response.status_code == 200
    data = response.json()
    assert data["models"] == {}
