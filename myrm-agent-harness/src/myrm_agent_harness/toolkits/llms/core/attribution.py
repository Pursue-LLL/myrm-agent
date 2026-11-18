"""Client attribution: the headers that name the calling app to OpenRouter and Vercel AI Gateway.

[INPUT]
- transport.params::merge_headers (POS: case-insensitive header merge in which the caller's names win)

[OUTPUT]
- ClientAttribution: the identity of the calling app (site URL, app name, OpenRouter categories, Vercel User-Agent)
- set_client_attribution(): register the identity for this process, or None to remove it
- openrouter_headers() / vercel_headers(): the header set each gateway documents for app attribution
- apply_client_attribution(): attach the registered identity to the request headers of a model bound for one of them

[POS]
Extension point between the model factory and the host that owns the product brand. The harness carries no brand of
its own: until a host registers an identity no attribution header is sent, so an application embedding the harness is
never announced as someone else's. Headers go to ``model_kwargs["extra_headers"]``, the only place the chat model reads
request headers from, and a header the caller set under the same name (in any letter case) is kept.

See: https://openrouter.ai/docs/app-attribution, https://vercel.com/docs/ai-gateway/ecosystem/app-attribution
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from myrm_agent_harness.toolkits.llms.transport.params import merge_headers

_OPENROUTER_HOST = "openrouter.ai"
_OPENROUTER_MODEL_PREFIX = "openrouter/"
_VERCEL_HOST = "ai-gateway.vercel.sh"


@dataclass(frozen=True)
class ClientAttribution:
    """The identity a host announces to gateways that rank or meter the apps calling them.

    ``site_url`` is the app's identifier on both gateways. ``openrouter_categories`` are OpenRouter's documented
    category ids; ``vercel_user_agent`` is sent to Vercel only. Every value ends up in an HTTP header, so each must be
    ASCII: ``httpx`` raises ``UnicodeEncodeError`` while building a request that carries anything else.
    """

    site_url: str
    app_name: str
    openrouter_categories: tuple[str, ...] = ()
    vercel_user_agent: str | None = None

    def __post_init__(self) -> None:
        header_values = (self.site_url, self.app_name, *self.openrouter_categories, self.vercel_user_agent or "")
        for value in header_values:
            if not value.isascii():
                raise ValueError(f"Attribution values are sent as HTTP headers and must be ASCII, got {value!r}")


def openrouter_headers(attribution: ClientAttribution) -> dict[str, str]:
    """OpenRouter's app-attribution headers: the referer identifies the app, title and categories describe it."""
    headers = {"HTTP-Referer": attribution.site_url, "X-OpenRouter-Title": attribution.app_name}
    if attribution.openrouter_categories:
        headers["X-OpenRouter-Categories"] = ",".join(attribution.openrouter_categories)
    return headers


def vercel_headers(attribution: ClientAttribution) -> dict[str, str]:
    """Vercel AI Gateway's app-attribution headers (it documents the referer and the title)."""
    headers = {"HTTP-Referer": attribution.site_url, "X-Title": attribution.app_name}
    if attribution.vercel_user_agent:
        headers["User-Agent"] = attribution.vercel_user_agent
    return headers


_registered: ClientAttribution | None = None


def set_client_attribution(attribution: ClientAttribution | None) -> None:
    """Register *attribution* for every model this process builds from now on, or remove it with None.

    Callers cache the models they build, so a host registers once at startup, before the first model exists.
    """
    global _registered
    _registered = attribution


def _gateway_headers(attribution: ClientAttribution, base_url: str | None, model: str) -> dict[str, str]:
    endpoint = (base_url or "").lower()
    headers: dict[str, str] = {}
    if _VERCEL_HOST in endpoint:
        headers.update(vercel_headers(attribution))
    if _OPENROUTER_HOST in endpoint or model.lower().startswith(_OPENROUTER_MODEL_PREFIX):
        headers.update(openrouter_headers(attribution))
    return headers


def apply_client_attribution(base_url: str | None, model: str, llm_kwargs: dict[str, object]) -> None:
    """Add the registered identity's headers to *llm_kwargs* when the call goes to OpenRouter or Vercel AI Gateway.

    A header the caller configured keeps its value. ``model_kwargs`` is replaced rather than edited: a caller may hand
    the same dict to several models.
    """
    if _registered is None:
        return
    headers = _gateway_headers(_registered, base_url, model)
    if not headers:
        return
    raw = llm_kwargs.get("model_kwargs")
    if raw is not None and not isinstance(raw, Mapping):
        return
    model_kwargs = dict(raw) if raw else {}
    configured = model_kwargs.get("extra_headers")
    model_kwargs["extra_headers"] = merge_headers(headers, configured if isinstance(configured, Mapping) else {})
    llm_kwargs["model_kwargs"] = model_kwargs
