"""The provider keys a competitor's ``.env`` can hand over: which variables count and how the file is read.

[INPUT]
- myrm_agent_harness transport PROFILES (POS: the key variables each provider reads)
- python-dotenv (POS: the ``.env`` grammar: quotes, ``export``, comments)

[OUTPUT]
- IMPORTABLE_PROVIDERS: provider id -> the display name the settings UI shows for it
- ENV_TO_PROVIDER_ID: key variable -> provider id
- read_env_secrets: the importable keys of one ``.env`` file

[POS]
The one list behind the migration preview (does the ``.env`` hold keys?), the payload's key names and the import itself,
so what the wizard announces is what the import brings. The variables are the ones the transport itself reads for a
provider (a key a competitor's ``.env`` shares with us is found by the same name) plus the aliases competitors use;
only providers a key alone makes usable are listed, never one that also needs an endpoint the ``.env`` does not carry
(Azure, Bedrock, any provider reached through a shared OpenAI endpoint).
"""

from __future__ import annotations

import io
from pathlib import Path

from dotenv import dotenv_values
from myrm_agent_harness.toolkits.llms.transport import PROFILES

# The providers a key alone makes usable, with their settings-UI display names (the frontend's ``providerCatalog.ts``).
IMPORTABLE_PROVIDERS: dict[str, str] = {
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "gemini": "Google Gemini",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "zai": "Z.AI (Zhipu AI)",
    "xai": "xAI",
    "ollama": "Ollama",
    "moonshot": "Moonshot AI",
    "lm_studio": "LM Studio",
    "groq": "Groq",
    "dashscope": "Dashscope (Qwen)",
    "minimax": "MiniMax",
    "mistral": "Mistral AI",
    "together_ai": "Together AI",
    "volcengine": "Doubao (Volcengine)",
    "fireworks_ai": "Fireworks AI",
    "perplexity": "Perplexity AI",
    "xiaomi_mimo": "Xiaomi MiMo",
    "vercel_ai_gateway": "Vercel AI Gateway",
}

# The key variables come from the transport's own table; Vercel's gateway has no profile of its own (it is reached
# through the OpenAI wire at a fixed endpoint), so its variables are named here.
ENV_TO_PROVIDER_ID: dict[str, str] = {
    env: provider_id
    for provider_id in IMPORTABLE_PROVIDERS
    if provider_id in PROFILES
    for env in PROFILES[provider_id].api_key_env
}
ENV_TO_PROVIDER_ID.update(
    {
        # Variable names other assistants use for a provider the transport names differently.
        "GLM_API_KEY": "zai",
        "KIMI_API_KEY": "moonshot",
        "XIAOMI_API_KEY": "xiaomi_mimo",
        "AI_GATEWAY_API_KEY": "vercel_ai_gateway",
        "VERCEL_AI_GATEWAY_KEY": "vercel_ai_gateway",
        "VERCEL_API_KEY": "vercel_ai_gateway",
    }
)


def read_env_secrets(env_path: Path) -> dict[str, str]:
    """The importable keys of a ``.env`` file, read by python-dotenv's grammar (quotes, ``export``, comments).

    Nothing is interpolated: ``${NAME}`` would otherwise read this process's environment into the result, and a
    reference left unresolved is not a key, so it is skipped.
    """
    try:
        content = env_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return {}

    values = dotenv_values(stream=io.StringIO(content), interpolate=False)
    secrets: dict[str, str] = {}
    for name, raw in values.items():
        value = (raw or "").strip()
        if name in ENV_TO_PROVIDER_ID and value and "${" not in value:
            secrets[name] = value
    return secrets
