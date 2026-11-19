"""Third-party gateways that document a request dialect of their own.

[INPUT]
- (standard library only)

[OUTPUT]
- Gateway: the gateways this module recognises
- gateway_of: the gateway an endpoint URL belongs to, decided by its host
- is_nvidia_deepseek_v4: whether a gateway and model id name the DeepSeek V4 family of NVIDIA's hosted API
- documented_output_ceiling: the largest ``max_tokens`` a gateway documents for a model, or None

[POS]
A provider that speaks the OpenAI chat body is one data row in ``profile.PROFILES``; the gateways here are hosts
that take that body but document their own way to switch thinking on and off and, for some models, a tighter
``max_tokens`` range than the model's own ceiling. They are told apart by host, which is what the WebUI presets point
at. A self-hosted or proxied endpoint is not recognised and keeps the generic rules, so a rule never fires on a
guess.
"""

from __future__ import annotations

from typing import Final, Literal
from urllib.parse import urlsplit

Gateway = Literal["siliconflow", "nvidia"]

_GATEWAY_HOSTS: Final[dict[str, Gateway]] = {
    "api.siliconflow.cn": "siliconflow",
    "api.siliconflow.com": "siliconflow",
    "integrate.api.nvidia.com": "nvidia",
}

# NVIDIA's hosted API documents ``max_tokens`` as 1 to 16384 for DeepSeek V4 (Flash and Pro) and answers 422 beyond it
# (https://docs.api.nvidia.com/nim/reference/deepseek-ai-deepseek-v4-flash-infer).
_NVIDIA_DEEPSEEK_V4_MAX_TOKENS: Final = 16_384


def gateway_of(base_url: str | None) -> Gateway | None:
    """The gateway ``base_url`` points at, or None when its host is not one this module knows."""
    if not base_url:
        return None
    try:
        host = urlsplit(base_url if "//" in base_url else f"//{base_url}").hostname
    except ValueError:  # a malformed URL (unbalanced IPv6 brackets) names no known host
        return None
    return _GATEWAY_HOSTS.get(host.lower()) if host else None


def is_nvidia_deepseek_v4(gateway: Gateway | None, model: str) -> bool:
    """Whether ``model`` is a DeepSeek V4 model of NVIDIA's hosted API, the family whose dialect and range it documents."""
    return gateway == "nvidia" and "deepseek-v4" in model.lower()


def documented_output_ceiling(base_url: str | None, model: str) -> int | None:
    """The largest ``max_tokens`` the endpoint documents for ``model``, or None when it documents none."""
    if is_nvidia_deepseek_v4(gateway_of(base_url), model):
        return _NVIDIA_DEEPSEEK_V4_MAX_TOKENS
    return None
