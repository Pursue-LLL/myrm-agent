"""Tests for how an endpoint URL is recognised as one of the gateways with a dialect of their own."""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.llms.transport.gateways import documented_output_ceiling, gateway_of


class TestGatewayOf:
    @pytest.mark.parametrize(
        ("base_url", "gateway"),
        [
            ("https://api.siliconflow.cn/v1", "siliconflow"),
            ("https://api.siliconflow.com/v1/", "siliconflow"),
            ("HTTPS://API.SILICONFLOW.CN/v1", "siliconflow"),
            ("https://integrate.api.nvidia.com/v1", "nvidia"),
            ("integrate.api.nvidia.com/v1", "nvidia"),
            ("https://integrate.api.nvidia.com:443/v1", "nvidia"),
        ],
    )
    def test_the_hosts_the_presets_point_at(self, base_url: str, gateway: str) -> None:
        assert gateway_of(base_url) == gateway

    @pytest.mark.parametrize(
        "base_url",
        [
            None,
            "",
            "https://opencode.ai/zen/go/v1",
            "http://127.0.0.1:8000/v1",
            # A host that merely contains a known one is not that gateway.
            "https://api.siliconflow.cn.evil.example/v1",
            "https://evil.example/api.siliconflow.cn/v1",
            "https://user@evil.example/?next=integrate.api.nvidia.com",
            "http://[::1/v1",
        ],
    )
    def test_anything_else_is_not_recognised(self, base_url: str | None) -> None:
        assert gateway_of(base_url) is None


class TestDocumentedOutputCeiling:
    @pytest.mark.parametrize(
        "model",
        [
            "openai/deepseek-ai/deepseek-v4-flash",
            "deepseek-ai/deepseek-v4-pro",
            "openai/DeepSeek-AI/DeepSeek-V4-Flash",
        ],
    )
    def test_nvidia_documents_a_range_for_deepseek_v4(self, model: str) -> None:
        assert documented_output_ceiling("https://integrate.api.nvidia.com/v1", model) == 16_384

    @pytest.mark.parametrize(
        ("base_url", "model"),
        [
            ("https://integrate.api.nvidia.com/v1", "meta/llama-3.3-70b-instruct"),
            ("https://integrate.api.nvidia.com/v1", "qwen/qwen3-next-80b-a3b-thinking"),
            ("https://api.siliconflow.cn/v1", "deepseek-ai/DeepSeek-V4-Flash"),
            ("https://api.deepseek.com/v1", "deepseek-v4-flash"),
            (None, "deepseek-ai/deepseek-v4-flash"),
        ],
    )
    def test_no_other_endpoint_or_model_has_a_documented_range(self, base_url: str | None, model: str) -> None:
        assert documented_output_ceiling(base_url, model) is None
