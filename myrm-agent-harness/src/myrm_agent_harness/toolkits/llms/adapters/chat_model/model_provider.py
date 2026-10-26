"""GenAI provider name of a ChatLiteLLM call.

[INPUT]
- litellm::get_llm_provider (POS: provider resolution from model id, custom provider and api_base)
- infra.tracing.gen_ai::provider_name (POS: LiteLLM provider id -> GenAI provider name)

[OUTPUT]
- model_provider_name: provider label of a model configuration, resolved once per configuration

[POS]
Telemetry label for the model-call span and metrics. A bare model id such as ``gpt-4o-mini`` carries
no provider prefix, so the provider is asked of LiteLLM (the component that will route the call)
instead of being guessed from the string; an unresolvable model falls back to its prefix.
"""

from __future__ import annotations

from functools import lru_cache

from myrm_agent_harness.infra.tracing.gen_ai import provider_name


@lru_cache(maxsize=256)
def model_provider_name(model: str, api_base: str | None, custom_llm_provider: str | None) -> str:
    """Provider label for ``model``; resolved once per (model, endpoint, provider) configuration."""
    resolved = custom_llm_provider
    try:
        import litellm

        resolved = litellm.get_llm_provider(
            model=model,
            custom_llm_provider=custom_llm_provider,
            api_base=api_base,
        )[1]
    except Exception:
        resolved = custom_llm_provider
    return provider_name(resolved, model)
