"""Registry of every intentional difference between where the previous client library sent a call and where the transport does.

[INPUT]
- (none) Pure data.

[OUTPUT]
- ShapeRule: one registered difference (providers, base shapes, scenarios, reason)
- SHAPE_RULES: the registry

[POS]
Companion of ``golden_shapes``. Cases are named ``family/provider|scenario|shape``. The golden shapes test fails on a
difference that no rule here covers and on a rule that covers nothing, so each entry states why the new endpoint is the
one wanted: the previous request could not have worked as written, or it is a change the other golden registries
already record for the default endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ShapeRule:
    id: str
    reason: str
    providers: tuple[str, ...] | None = None  # None: every provider
    shapes: tuple[str, ...] | None = None  # None: every shape of base URL
    scenarios: tuple[str, ...] | None = None  # None: every scenario


_CHAT_PASTED_URL = (
    "chat/azure",
    "chat/cerebras",
    "chat/dashscope",
    "chat/lm_studio",
    "chat/mistral",
    "chat/moonshot",
    "chat/openai",
    "chat/perplexity",
    "chat/together_ai",
    "chat/volcengine",
    "chat/xai",
    "chat/xiaomi_mimo",
    "chat/yunshu",
    "chat/zai",
)

SHAPE_RULES: tuple[ShapeRule, ...] = (
    ShapeRule(
        "pasted-chat-url-appended-again",
        "A base saved as the whole chat URL was extended with the call's own path again: `/v1/chat/completions/chat/"
        "completions`, `.../completions/v1` for Mistral, `.../completions/responses` for xAI, `.../completions/openai/"
        "deployments/...` for Azure. The transport cuts the pasted operation, as it does for every provider.",
        providers=_CHAT_PASTED_URL,
        shapes=("full_chat", "full_chat_gw"),
    ),
    ShapeRule(
        "pasted-operation-url-appended-again",
        "A base saved as the whole URL of an embedding, rerank or image operation was extended with the operation "
        "again (`/v1/embeddings/embeddings`, `/v1/images/generations/images/edits`, `/v1/rerank/rerank`); the "
        "transport cuts the pasted operation.",
        shapes=("full_op",),
    ),
    ShapeRule(
        "trailing-slash-misread",
        "A base ending in `/` was joined to the call's path as it stood (`//v1/messages`, `/v1//chat/completions`, "
        "`/v1//rerank`), and for MiniMax the `/v1` check missed the slash and appended a second `/v1`. The transport "
        "drops the trailing slash first.",
        providers=(
            "chat/anthropic",
            "chat/deepseek",
            "chat/gemini",
            "chat/minimax",
            "chat/mistral",
            "rerank/openai_compat",
        ),
        shapes=("slash", "v1slash"),
    ),
    ShapeRule(
        "anthropic-version-segment-doubled",
        "A base that already ends in `/v1` got the wire's `/v1/messages` appended (`/v1/v1/messages`); the transport "
        "reads the base as the root the wire appends its own `/v1/messages` to.",
        providers=("chat/anthropic",),
        shapes=("v1", "gw_v1"),
    ),
    ShapeRule(
        "ollama-chat-endpoint",
        "Same decision as the golden request registry's `ollama-endpoint`: chat goes to `/api/chat`, not "
        "`/api/generate`. Every shape follows it, and a pasted `/v1`, `/api` or operation suffix is cut instead of "
        "being stacked under the new path (`/v1/api/generate`, `/api/api/generate`).",
        providers=("chat/ollama",),
    ),
    ShapeRule(
        "cohere-compatibility-endpoint",
        "Same decision as the golden request registry's rule of that name: Cohere chat goes through its OpenAI-"
        "compatible endpoint, so the transport appends `/chat/completions` where the previous library posted to the "
        "base URL itself.",
        providers=("chat/cohere_chat",),
    ),
    ShapeRule(
        "flux-settings-alias",
        "Same decision as the golden services registry's rule of that name: the previous library rejected `flux/"
        "schnell` before sending anything, so it reached no endpoint; the transport maps it to Together's FLUX.1.",
        providers=("image/flux",),
    ),
    ShapeRule(
        "image-edit-refused-before-sending",
        "Same decision as the golden services registry's rule of that name: Image edit is not offered for Gemini "
        "Imagen and Stability; the previous library sent a request and failed, the transport refuses before sending.",
        providers=("image/gemini_imagen", "image/stability"),
        scenarios=("edit",),
    ),
    ShapeRule(
        "image-edit-attempted-for-xai-together",
        "Same decision as the golden services registry's rule of that name: edit is not offered for xAI and Together, "
        "so the previous library refused it up front; called directly, the transport sends `/images/edits`.",
        providers=("image/xai", "image/together_flux"),
        scenarios=("edit",),
    ),
    ShapeRule(
        "together-rerank-honours-base",
        "Same decision as the golden services registry's rule of that name: the previous library ignored the given "
        "base and called api.together.xyz; the transport calls the configured endpoint.",
        providers=("rerank/together_ai",),
    ),
    ShapeRule(
        "azure-ai-rerank-endpoint",
        "The settings do not offer Azure AI rerank and the transport has no `azure_ai` provider, so the id goes to "
        "the given endpoint with `/rerank` appended; for a base that stops short of `/v1` the previous library "
        "completed it to `/v1/rerank`.",
        providers=("rerank/azure_ai",),
        shapes=("bare", "slash", "gw"),
    ),
    ShapeRule(
        "cohere-rerank-keeps-the-bases-version",
        "A base that already names a version got Cohere's `/v2/rerank` appended (`/v1/v2/rerank`); the transport "
        "uses the version the base names, and adds `/v2` only to a base that names none.",
        providers=("rerank/cohere",),
        shapes=("v1", "v1slash", "gw_v1"),
    ),
    ShapeRule(
        "jina-rerank-keeps-the-gateway-prefix",
        "The previous library dropped a gateway prefix from a Jina endpoint (`/gw` and `/gw/v1` both became "
        "`/v1/rerank`), so a gateway never saw its own path; the transport keeps it (`/gw/v1/rerank`).",
        providers=("rerank/jina_ai",),
        shapes=("gw", "gw_v1"),
    ),
)
