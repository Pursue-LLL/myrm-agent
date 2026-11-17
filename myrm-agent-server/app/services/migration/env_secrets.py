"""The provider keys a competitor's ``.env`` can hand over: which variables count and how the file is read.

[INPUT]
- myrm_agent_harness transport PROFILES (POS: the key variables each provider reads)
- python-dotenv (POS: the ``.env`` grammar: quotes, ``export``, comments)

[OUTPUT]
- IMPORTABLE_PROVIDERS: provider id -> the display name the settings UI shows for it
- MULTI_ENDPOINT_PROVIDERS: the importable providers whose key is bound to one of several endpoints (regions, plans)
- ENV_TO_PROVIDER_ID: key variable -> provider id
- KEY_FROM_ENV / KEY_FROM_AUTH: where a payload's key name comes from (the ``.env`` the import reads, or a credential store)
- EnvKeys / read_env_keys: the keys of one ``.env`` file the import reads, and the names of the key variables it leaves alone

[POS]
The one list behind the migration preview (does the ``.env`` hold keys?), the payload's key names and the import itself,
so what the wizard announces is what the import brings. The variables are the ones the transport itself reads for a
provider (a key a competitor's ``.env`` shares with us is found by the same name) plus the aliases competitors use;
only providers a key alone makes usable are listed, never one that also needs an endpoint the ``.env`` does not carry
(Azure, Bedrock, any provider reached through a shared OpenAI endpoint). A key variable outside the list is not dropped
silently: its name is reported so the user can enter that key by hand.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path

from dotenv import dotenv_values
from myrm_agent_harness.toolkits.llms.transport import PROFILES

# Where a payload's key name comes from: the ``.env`` the import reads, or a credential store (Hermes ``auth.json``, Pi
# ``auth.json``) it does not.
KEY_FROM_ENV = "env"
KEY_FROM_AUTH = "auth"

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

# Providers whose settings entry offers several endpoints (regions or plans) with different defaults. A key belongs to
# one of them and the ``.env`` does not say which, so the import never creates one of these from a key alone: a row at
# the wrong endpoint looks configured and then fails on its first call. Keys for a row the user already has go in as usual.
MULTI_ENDPOINT_PROVIDERS = frozenset({"zai", "moonshot", "dashscope", "minimax", "xiaomi_mimo"})

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


# Every key variable the transport knows, whether or not the import fills its provider.
_PROVIDER_KEY_VARIABLES = frozenset(env for profile in PROFILES.values() for env in profile.api_key_env)


@dataclass(frozen=True)
class EnvKeys:
    """The provider keys one ``.env`` holds."""

    # Variable -> key, for the variables the import reads.
    importable: dict[str, str]
    # Names, never values, of the other key variables: the import has no provider to put them in.
    unsupported: tuple[str, ...]


def read_env_keys(env_path: Path) -> EnvKeys:
    """The keys of a ``.env`` file, read by python-dotenv's grammar (quotes, ``export``, comments).

    Nothing is interpolated: ``${NAME}`` would otherwise read this process's environment into the result, and a
    reference left unresolved is not a key, so it is skipped. A variable counts as a key variable when it ends in
    ``_API_KEY`` or is one the transport reads for a provider.
    """
    try:
        content = env_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return EnvKeys(importable={}, unsupported=())

    importable: dict[str, str] = {}
    unsupported: list[str] = []
    for name, raw in dotenv_values(stream=io.StringIO(content), interpolate=False).items():
        value = (raw or "").strip()
        if not value or "${" in value:
            continue
        if name in ENV_TO_PROVIDER_ID:
            importable[name] = value
        elif name.endswith("_API_KEY") or name in _PROVIDER_KEY_VARIABLES:
            unsupported.append(name)
    return EnvKeys(importable=importable, unsupported=tuple(unsupported))
