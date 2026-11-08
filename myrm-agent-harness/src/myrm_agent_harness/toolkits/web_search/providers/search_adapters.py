"""Request and response shapes of the REST search providers.

[INPUT]
- (none) Pure dict transforms.

[OUTPUT]
- SearchRequest: one provider HTTP request (method, URL, headers, JSON body or query)
- SearchAdapter: how one provider builds its request from the unified query and reads its answer
- ADAPTERS: adapters keyed by provider slug (perplexity, tavily, exa_ai, parallel_ai, google_pse, dataforseo,
  firecrawl, searxng, brave, serper)

[POS]
The provider-specific half of the REST search client. Every provider is described by two functions: ``build``
maps the unified parameters (``max_results``, ``search_domain_filter``, ``country``) and the caller's provider
parameters onto the provider's request, ``parse`` maps its answer onto ``{title, url, snippet, date}`` rows. A
caller's parameter never overrides a field the unified parameters already set, and a parameter a provider does not
know is passed through untouched, so provider-specific options reach the provider without this module knowing them.
"""

from __future__ import annotations

import base64
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Final, Literal

from myrm_agent_harness.toolkits.web_search.core.exceptions import SearchConfigError

Row = dict[str, str | None]
Unified = Mapping[str, object]

# Parameters of the unified search spec; they are mapped, never passed through under their own names.
_UNIFIED_KEYS: Final = frozenset({"max_results", "search_domain_filter", "country", "max_tokens_per_page"})
_DATAFORSEO_DEFAULT_LOCATION_CODE: Final = 2250
_BRAVE_SECTIONS: Final = ("web", "discussions", "faqs", "faq", "news", "videos")
_ISO_DATE: Final = re.compile(r"^\d{4}-\d{2}-\d{2}")
_SEARXNG_LANGUAGES: Final = {"us": "en", "uk": "en", "de": "de", "fr": "fr", "es": "es", "jp": "ja"}


@dataclass(frozen=True, slots=True)
class SearchRequest:
    """One provider HTTP request."""

    method: Literal["GET", "POST"]
    url: str
    headers: dict[str, str]
    json_body: object | None = None
    params: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SearchAdapter:
    build: Callable[[str, int, Unified, str | None, str | None], SearchRequest]
    parse: Callable[[Mapping[str, object], SearchRequest], list[Row]]


def _list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _dicts(value: object) -> list[Mapping[str, object]]:
    return [item for item in _list(value) if isinstance(item, Mapping)]


def _text(value: object) -> str:
    return value if isinstance(value, str) else ""


def _opt_text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _domains(unified: Unified) -> list[str]:
    value = unified.get("search_domain_filter")
    if isinstance(value, str):
        return [value]
    return [d for d in _list(value) if isinstance(d, str)]


def _country(unified: Unified) -> str | None:
    return _opt_text(unified.get("country"))


def _merge(fields: dict[str, object], unified: Unified) -> dict[str, object]:
    """``fields`` plus the caller's provider parameters that no mapped field already claims."""
    merged = dict(fields)
    for key, value in unified.items():
        if key not in _UNIFIED_KEYS and key not in merged:
            merged[key] = value
    return merged


def _url(api_base: str | None, default: str, suffix: str) -> str:
    base = (api_base or default).rstrip("/")
    return base if base.endswith(suffix) else f"{base}{suffix}"


def _bearer(api_key: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"} if api_key else {}


def _post(url: str, headers: dict[str, str], body: object) -> SearchRequest:
    return SearchRequest("POST", url, {**headers, "Content-Type": "application/json"}, json_body=body)


def _row(title: object, url: object, snippet: object, date: object = None) -> Row:
    return {"title": _text(title), "url": _text(url), "snippet": _text(snippet), "date": _opt_text(date)}


def _require_key(api_key: str | None, provider: str) -> str:
    if not api_key:
        raise SearchConfigError(f"{provider} search requires an API key", config_key="api_key")
    return api_key


# --- Perplexity ----------------------------------------------------------------------------------------------


def _perplexity_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    body: dict[str, object] = {"query": query, "max_results": limit}
    for name in ("search_domain_filter", "max_tokens_per_page", "country"):
        if unified.get(name) is not None:
            body[name] = unified[name]
    return _post(_url(base, "https://api.perplexity.ai", "/search"), _bearer(_require_key(key, "perplexity")), body)


def _perplexity_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    return [_row(r.get("title"), r.get("url"), r.get("snippet"), r.get("date")) for r in _dicts(payload.get("results"))]


# --- Tavily --------------------------------------------------------------------------------------------------


def _tavily_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    fields: dict[str, object] = {"query": query, "max_results": limit}
    if domains := _domains(unified):
        fields["include_domains"] = domains
    if country := _country(unified):
        fields["country"] = country.lower()
    return _post(
        _url(base, "https://api.tavily.com", "/search"), _bearer(_require_key(key, "tavily")), _merge(fields, unified)
    )


def _tavily_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    return [_row(r.get("title"), r.get("url"), r.get("content")) for r in _dicts(payload.get("results"))]


# --- Exa -----------------------------------------------------------------------------------------------------


def _exa_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    fields: dict[str, object] = {"query": query, "numResults": limit}
    if domains := _domains(unified):
        fields["includeDomains"] = domains
    if country := _country(unified):
        fields["userLocation"] = country
    body = _merge(fields, unified)
    body.setdefault("contents", {"text": True})
    return _post(_url(base, "https://api.exa.ai", "/search"), {"x-api-key": _require_key(key, "exa_ai")}, body)


def _exa_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    rows: list[Row] = []
    for r in _dicts(payload.get("results")):
        highlights = "\n\n".join(h for h in _list(r.get("highlights")) if isinstance(h, str))
        snippet = _text(r.get("text")) or highlights or _text(r.get("summary"))
        rows.append(_row(r.get("title"), r.get("url"), snippet, r.get("publishedDate")))
    return rows


# --- Parallel ------------------------------------------------------------------------------------------------

_PARALLEL_LEGACY_MODES: Final = {"base": "basic", "pro": "advanced"}


def _parallel_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    params = dict(unified)
    mode = params.pop("mode", None)
    processor = params.pop("processor", None)
    if mode is None and isinstance(processor, str):
        mode = _PARALLEL_LEGACY_MODES.get(processor, processor)
    advanced: dict[str, object] = {"max_results": params.pop("max_results", limit)}
    if country := params.pop("country", None):
        advanced["location"] = country
    if (chars := params.pop("max_chars_per_result", None)) is not None:
        advanced["excerpt_settings"] = {"max_chars_per_result": chars}
    policy: dict[str, object] = {}
    if (include := params.pop("search_domain_filter", None)) is not None:
        policy["include_domains"] = include
    if (exclude := params.pop("exclude_domains", None)) is not None:
        policy["exclude_domains"] = exclude
    if policy:
        advanced["source_policy"] = policy
    overrides = params.pop("advanced_settings", None)
    if isinstance(overrides, Mapping):
        advanced.update(overrides)
    params.pop("max_tokens_per_page", None)
    body: dict[str, object] = {
        "search_queries": [query],
        "objective": query,
        "mode": mode or "basic",
        "advanced_settings": advanced,
    }
    body.update(params)
    root = (base or "https://api.parallel.ai").rstrip("/")
    url = root if root.endswith("/v1/search") else f"{root.removesuffix('/v1')}/v1/search"
    return _post(url, {"x-api-key": _require_key(key, "parallel_ai")}, body)


def _parallel_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    rows: list[Row] = []
    for r in _dicts(payload.get("results")):
        excerpts = " ... ".join(e for e in _list(r.get("excerpts")) if isinstance(e, str))
        rows.append(_row(r.get("title"), r.get("url"), excerpts, r.get("publish_date")))
    return rows


# --- Google Programmable Search ------------------------------------------------------------------------------


def _google_pse_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    engine = unified.get("search_engine_id") or unified.get("cx")
    if not isinstance(engine, str) or not engine:
        raise SearchConfigError(
            "google_pse search requires a search engine id (extra_params.search_engine_id)",
            config_key="search_engine_id",
        )
    fields: dict[str, object] = {
        "q": query,
        "cx": engine,
        "key": _require_key(key, "google_pse"),
        "num": min(limit, 10),
    }
    if domains := _domains(unified):
        fields["siteSearch"] = domains[0]
        fields["siteSearchFilter"] = "i"
    if country := _country(unified):
        fields["gl"] = country.upper()
    params = _merge(fields, {k: v for k, v in unified.items() if k not in {"search_engine_id", "cx"}})
    return SearchRequest("GET", base or "https://www.googleapis.com/customsearch/v1", {}, params=params)


def _google_pse_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    return [_row(r.get("title"), r.get("link"), r.get("snippet")) for r in _dicts(payload.get("items"))]


# --- DataForSEO ----------------------------------------------------------------------------------------------


def _dataforseo_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    login, separator, password = _require_key(key, "dataforseo").partition(":")
    if not separator or not login or not password:
        raise SearchConfigError(
            "dataforseo search requires an API key of the form 'login:password'", config_key="api_key"
        )
    task: dict[str, object] = {"keyword": query, "depth": min(limit, 700)}
    if country := _country(unified):
        task["location_name"] = country
    if domains := unified.get("search_domain_filter"):
        task["domain"] = domains
    task = _merge(task, unified)
    if "language_code" not in task and "language_name" not in task:
        task["language_code"] = "en"
    if "location_code" not in task and "location_name" not in task:
        task["location_code"] = _DATAFORSEO_DEFAULT_LOCATION_CODE
    credentials = base64.b64encode(f"{login}:{password}".encode()).decode()
    url = base or "https://api.dataforseo.com/v3/serp/google/organic/live/advanced"
    return _post(url, {"Authorization": f"Basic {credentials}"}, [task])


def _dataforseo_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    for task in _dicts(payload.get("tasks"))[:1]:
        if task.get("status_code") != 20000:
            continue
        for result in _dicts(task.get("result"))[:1]:
            return [
                _row(item.get("title"), item.get("url"), item.get("description"))
                for item in _dicts(result.get("items"))
                if item.get("type") == "organic"
            ]
    return []


# --- Firecrawl -----------------------------------------------------------------------------------------------


def _firecrawl_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    fields: dict[str, object] = {"query": query, "limit": limit}
    if country := _country(unified):
        fields["country"] = country
    body = _merge(fields, unified)
    body.setdefault("scrapeOptions", {"formats": ["markdown"], "onlyMainContent": True})
    return _post(_url(base, "https://api.firecrawl.dev/v2", "/search"), _bearer(_require_key(key, "firecrawl")), body)


def _firecrawl_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    data = payload.get("data")
    if isinstance(data, list):
        return [_row(r.get("title"), r.get("url"), r.get("markdown") or r.get("description")) for r in _dicts(data)]
    if not isinstance(data, Mapping):
        return []
    web = [
        _row(r.get("title"), r.get("url"), r.get("markdown") or r.get("description")) for r in _dicts(data.get("web"))
    ]
    news = [
        _row(r.get("title"), r.get("url"), r.get("markdown") or r.get("snippet"), r.get("date"))
        for r in _dicts(data.get("news"))
    ]
    return web + news


# --- SearXNG -------------------------------------------------------------------------------------------------


def _searxng_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    if not base:
        raise SearchConfigError("searxng search requires an api_base", config_key="api_base")
    fields: dict[str, object] = {"q": query, "format": "json"}
    if country := _country(unified):
        fields["language"] = _SEARXNG_LANGUAGES.get(country.lower(), country.lower())
    return SearchRequest("GET", _url(base, "", "/search"), _bearer(key), params=_merge(fields, unified))


def _searxng_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    return [
        _row(r.get("title"), r.get("url"), r.get("content"), r.get("publishedDate") or r.get("pubdate"))
        for r in _dicts(payload.get("results"))
    ]


# --- Brave ---------------------------------------------------------------------------------------------------


def _brave_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    domains = _domains(unified)
    if domains:
        sites = " OR ".join(f"site:{d}" for d in domains)
        query = f"({query}) AND ({sites})"
    fields: dict[str, object] = {
        "q": query,
        "count": min(limit, 20),
        "include_fetch_metadata": unified.get("include_fetch_metadata") is not False,
    }
    params = _merge(fields, unified)
    headers = {"X-Subscription-Token": _require_key(key, "brave"), "Accept": "application/json"}
    return SearchRequest("GET", base or "https://api.search.brave.com/res/v1/web/search", headers, params=params)


def _brave_date(value: object) -> str | None:
    """The ISO day of a machine-readable page age; a relative age ("2 days ago") has no day to report."""
    return value[:10] if isinstance(value, str) and _ISO_DATE.match(value) else None


def _brave_parse(payload: Mapping[str, object], request: SearchRequest) -> list[Row]:
    requested = str(request.params.get("result_filter") or "")
    wanted = [s.strip().lower() for s in requested.split(",")]
    sections = [s for s in wanted if s in _BRAVE_SECTIONS] or list(_BRAVE_SECTIONS)
    limit = max(1, min(int(str(request.params.get("count", 20))), 20))
    rows: list[Row] = []
    for section in sections:
        block = payload.get(section)
        for r in _dicts(block.get("results") if isinstance(block, Mapping) else None):
            if len(rows) >= limit:
                return rows
            rows.append(_row(r.get("title"), r.get("url"), r.get("description"), _brave_date(r.get("page_age"))))
    return rows


# --- Serper --------------------------------------------------------------------------------------------------


def _serper_build(query: str, limit: int, unified: Unified, key: str | None, base: str | None) -> SearchRequest:
    domains = _domains(unified)
    if domains:
        query = f"({query}) ({' OR '.join(f'site:{d}' for d in domains)})"
    fields: dict[str, object] = {"q": query, "num": limit}
    if country := _country(unified):
        fields["gl"] = country.lower()
    return _post(
        _url(base, "https://google.serper.dev", "/search"),
        {"X-API-KEY": _require_key(key, "serper")},
        _merge(fields, unified),
    )


def _serper_parse(payload: Mapping[str, object], _: SearchRequest) -> list[Row]:
    return [
        _row(r.get("title"), r.get("link"), r.get("snippet"), r.get("date")) for r in _dicts(payload.get("organic"))
    ]


ADAPTERS: Final[dict[str, SearchAdapter]] = {
    "perplexity": SearchAdapter(_perplexity_build, _perplexity_parse),
    "tavily": SearchAdapter(_tavily_build, _tavily_parse),
    "exa_ai": SearchAdapter(_exa_build, _exa_parse),
    "parallel_ai": SearchAdapter(_parallel_build, _parallel_parse),
    "google_pse": SearchAdapter(_google_pse_build, _google_pse_parse),
    "dataforseo": SearchAdapter(_dataforseo_build, _dataforseo_parse),
    "firecrawl": SearchAdapter(_firecrawl_build, _firecrawl_parse),
    "searxng": SearchAdapter(_searxng_build, _searxng_parse),
    "brave": SearchAdapter(_brave_build, _brave_parse),
    "serper": SearchAdapter(_serper_build, _serper_parse),
}
