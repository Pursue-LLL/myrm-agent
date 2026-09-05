"""Server wire registry unit tests."""

from app.core.types import ModelConfig
from app.core.wire.enrich import enrich_model_config
from app.core.wire.registry import normalize_model_name_for_wire, resolve_wire_protocol

_OPENCODE_BASE = "https://opencode.ai/zen/go/v1"
_OTHER_BASE = "https://api.deepseek.com/v1"
_PROXY_BASE = "https://llm-proxy.company.com/v1"


def test_muse_spark_responses_on_opencode() -> None:
    assert resolve_wire_protocol("openai/muse-spark-1.2-contributor", _OPENCODE_BASE) == "responses"


def test_gpt_luna_responses_on_opencode() -> None:
    assert resolve_wire_protocol("openai/gpt-5.6-luna", _OPENCODE_BASE) == "responses"


def test_qwen_anthropic_messages_on_opencode() -> None:
    assert resolve_wire_protocol("openai/qwen3.6-plus", _OPENCODE_BASE) == "anthropic_messages"


def test_qwen_stays_chat_on_non_opencode() -> None:
    assert resolve_wire_protocol("openai/qwen-max", _OTHER_BASE) == "chat_completions"


def test_deepseek_chat_completions() -> None:
    assert resolve_wire_protocol("openai/deepseek-v4-flash", _OPENCODE_BASE) == "chat_completions"


def test_muse_spark_responses_via_provider_id_on_proxy_url() -> None:
    assert (
        resolve_wire_protocol(
            "openai/muse-spark-1.2-contributor",
            _PROXY_BASE,
            provider_id="opencode_go",
        )
        == "responses"
    )


def test_qwen_stays_chat_on_proxy_without_opencode_provider() -> None:
    assert resolve_wire_protocol("openai/qwen-max", _PROXY_BASE) == "chat_completions"


def test_normalize_free_suffix() -> None:
    assert normalize_model_name_for_wire("openai/muse-spark-1.2-contributor-free") == "muse-spark-1.2-contributor"


def test_enrich_applies_provider_id_gate() -> None:
    cfg = enrich_model_config(
        ModelConfig(model="openai/muse-spark-1.2-contributor", api_key="sk-test", base_url=_PROXY_BASE),
        provider_id="opencode_go",
    )
    assert cfg.wire_protocol == "responses"
    extra_body = cfg.model_kwargs.get("extra_body") if cfg.model_kwargs else None
    assert isinstance(extra_body, dict)
    assert extra_body.get("include") == ["reasoning.encrypted_content"]
    assert extra_body.get("reasoning") == {"effort": "low"}


def test_enrich_applies_vercel_ai_gateway_defaults() -> None:
    cfg = enrich_model_config(
        ModelConfig(
            model="openai/anthropic/claude-3-5-sonnet",
            api_key="vca_secret",
            base_url="https://ai-gateway.vercel.sh/v1",
        ),
        provider_id="vercel_ai_gateway",
    )
    assert cfg.wire_protocol == "chat_completions"
    assert cfg.model_kwargs.get("custom_llm_provider") == "openai"
    headers = cfg.model_kwargs.get("extra_headers")
    assert isinstance(headers, dict)
    assert headers.get("HTTP-Referer") == "https://myrm.ai"
    assert headers.get("X-Title") == "Myrm Agent"
    assert "Vercel-AI-Gateway-Client" in headers.get("User-Agent", "")

