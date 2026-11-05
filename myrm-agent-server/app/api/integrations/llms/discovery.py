"""[OUTPUT]
discovery endpoints.

[POS]
Model discovery: probe an OpenAI-compatible endpoint and return its model IDs.
"""

from __future__ import annotations

import ipaddress
import json
from urllib.parse import urlparse, urlunparse

import httpx
from fastapi.responses import JSONResponse
from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.core.security.http.secure_fetch import secure_request
from myrm_agent_harness.infra.tls_compat import create_httpx_client
from pydantic import BaseModel, Field

from app.config.deploy_mode import is_local_mode
from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse

from .common import _LOCAL_NO_AUTH_KEY_MARKER, router

_MODELS_DISCOVERY_TIMEOUT_S = 8.0


_KNOWN_ENDPOINT_SUFFIXES = (
    "/chat/completions",
    "/completions",
    "/embeddings",
    "/models",
)


def _normalize_api_base(raw_url: str) -> str:
    candidate = raw_url.strip()
    if not candidate:
        raise ValueError("API URL is required")

    if "://" not in candidate:
        candidate = f"http://{candidate}"

    parsed = urlparse(candidate)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("API URL must use http or https")
    if not parsed.netloc:
        raise ValueError("API URL must include a hostname")

    path = parsed.path.rstrip("/")
    for suffix in _KNOWN_ENDPOINT_SUFFIXES:
        if path.endswith(suffix):
            path = path[: -len(suffix)]
            break

    normalized = parsed._replace(path=path, params="", query="", fragment="")
    return urlunparse(normalized).rstrip("/")


def _build_models_candidates(base_url: str) -> list[str]:
    base = base_url.rstrip("/")
    parsed = urlparse(base)
    path = parsed.path.rstrip("/")
    candidates: list[str] = []

    if path.endswith("/models"):
        candidates.append(base)

    if path:
        parts = [p for p in path.split("/") if p]
        if parts:
            parent1 = "/" + "/".join(parts[:-1]) if len(parts) > 1 else ""
            parent2 = "/" + "/".join(parts[:-2]) if len(parts) > 2 else ""
            candidates.append(urlunparse(parsed._replace(path=(parent1 + "/models") if parent1 else "/models")))
            if parent2:
                candidates.append(urlunparse(parsed._replace(path=f"{parent2}/models")))

    if not path:
        candidates.append(urlunparse(parsed._replace(path="/v1/models")))
        candidates.append(urlunparse(parsed._replace(path="/api/v1/models")))
        candidates.append(urlunparse(parsed._replace(path="/api/models")))

    candidates.append(urlunparse(parsed._replace(path=f"{path}/models" if path else "/models")))
    deduped = list(dict.fromkeys(candidates))
    return [url.rstrip("/") for url in deduped]


def _extract_model_ids(payload: object) -> list[str]:
    if isinstance(payload, dict):
        raw_data = payload.get("data")
        if isinstance(raw_data, list):
            return [str(item.get("id")) for item in raw_data if isinstance(item, dict) and item.get("id")]
        raw_models = payload.get("models")
        if isinstance(raw_models, list):
            return [str(item.get("id")) for item in raw_models if isinstance(item, dict) and item.get("id")]
    if isinstance(payload, list):
        return [str(item.get("id")) for item in payload if isinstance(item, dict) and item.get("id")]
    return []


def _is_loopback_host(hostname: str | None) -> bool:
    if not hostname:
        return False
    lowered = hostname.lower().strip("[]")
    if lowered == "localhost":
        return True
    try:
        parsed_ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False
    return parsed_ip.is_loopback or parsed_ip.is_unspecified


def _is_trusted_split_stack_host(hostname: str | None) -> bool:
    """Check if a hostname represents a loopback, RFC1918 private LAN, Tailscale CGNAT, or .local mDNS host.

    Excludes 169.254.0.0/16 (link-local cloud metadata) to prevent SSRF credential theft.
    """
    if not hostname:
        return False
    lowered = hostname.lower().strip("[]")
    if lowered == "localhost" or lowered.endswith(".local"):
        return True

    try:
        parsed_ip = ipaddress.ip_address(lowered)
    except ValueError:
        return False

    v4 = parsed_ip.ipv4_mapped if isinstance(parsed_ip, ipaddress.IPv6Address) else parsed_ip
    ip_to_check = v4 or parsed_ip

    # Explicitly block link-local cloud metadata endpoints (e.g. 169.254.169.254)
    if ip_to_check.is_link_local or (isinstance(ip_to_check, ipaddress.IPv4Address) and ip_to_check in _LINK_LOCAL_IPV4_NETWORK):
        return False

    if ip_to_check.is_loopback or ip_to_check.is_unspecified:
        return True

    if ip_to_check.is_private:
        return True

    if isinstance(ip_to_check, ipaddress.IPv4Address) and ip_to_check in _TAILSCALE_CGNAT_NETWORK:
        return True

    return False


_TAILSCALE_CGNAT_NETWORK = ipaddress.ip_network("100.64.0.0/10")
_LINK_LOCAL_IPV4_NETWORK = ipaddress.ip_network("169.254.0.0/16")


class ModelDiscoveryRequest(BaseModel):
    api_url: str = Field(..., min_length=1, description="OpenAI-compatible API base URL or endpoint URL")
    api_key: str | None = Field(default=None, description="Optional API key (required for non-local endpoints)")


class ModelDiscoveryResult(BaseModel):
    success: bool = Field(..., description="Whether model discovery succeeded")
    normalized_api_url: str = Field(..., description="Normalized API base URL")
    models_url: str | None = Field(default=None, description="Resolved models endpoint URL")
    models: list[str] = Field(default_factory=list, description="Discovered model IDs")
    no_auth_local: bool = Field(default=False, description="Whether no-auth local policy was used")
    error: str | None = Field(default=None, description="Error message when discovery fails")


@router.post("/discover-models", response_model=StandardSuccessResponse)
async def discover_models(request: ModelDiscoveryRequest) -> JSONResponse:
    """Discover model IDs from an OpenAI-compatible endpoint.

    Uses server-side SSRF-guarded probing to avoid exposing the frontend
    proxy to arbitrary URL fetches. Supports no-auth local endpoints in
    local/tauri deploy mode only.
    """

    try:
        normalized_api_url = _normalize_api_base(request.api_url)
    except ValueError as exc:
        result = ModelDiscoveryResult(
            success=False,
            normalized_api_url=request.api_url.strip(),
            error=str(exc),
        )
        return success_response(data=result.model_dump())

    parsed = urlparse(normalized_api_url)
    is_split_stack = _is_trusted_split_stack_host(parsed.hostname)
    api_key = (request.api_key or "").strip()
    use_no_auth_local = False
    if not api_key:
        if is_split_stack and is_local_mode():
            use_no_auth_local = True
            api_key = _LOCAL_NO_AUTH_KEY_MARKER
        else:
            result = ModelDiscoveryResult(
                success=False,
                normalized_api_url=normalized_api_url,
                error="API key is required for non-local endpoints",
            )
            return success_response(data=result.model_dump())

    headers: dict[str, str] = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if not use_no_auth_local:
        headers["Authorization"] = f"Bearer {api_key}"
    if parsed.hostname and "ai-gateway.vercel.sh" in parsed.hostname.lower():
        headers["HTTP-Referer"] = "https://myrm.ai"
        headers["X-Title"] = "Myrm Agent"
        headers["User-Agent"] = "Myrm/1.0 (Vercel-AI-Gateway-Client)"

    candidates = _build_models_candidates(normalized_api_url)
    last_error: str | None = None
    hostname = parsed.hostname
    allowed_hosts = [hostname] if hostname and is_split_stack and is_local_mode() else None

    async with create_httpx_client(timeout=_MODELS_DISCOVERY_TIMEOUT_S, follow_redirects=False) as client:
        for models_url in candidates:
            response: httpx.Response | None = None
            try:
                response = await secure_request(
                    client,
                    "GET",
                    models_url,
                    headers=headers,
                    timeout=_MODELS_DISCOVERY_TIMEOUT_S,
                    allowed_internal_hosts=allowed_hosts,
                )
                raw_bytes = await response.aread()
                text_payload = raw_bytes.decode("utf-8", errors="replace")
                if response.status_code >= 400:
                    last_error = f"Provider returned {response.status_code}: {text_payload[:200]}"
                    continue

                payload = json.loads(text_payload)
                model_ids = _extract_model_ids(payload)
                result = ModelDiscoveryResult(
                    success=True,
                    normalized_api_url=normalized_api_url,
                    models_url=models_url,
                    models=model_ids,
                    no_auth_local=use_no_auth_local,
                )
                return success_response(data=result.model_dump())
            except SSRFSecurityError as exc:
                result = ModelDiscoveryResult(
                    success=False,
                    normalized_api_url=normalized_api_url,
                    error=f"SSRF blocked: {exc}",
                )
                return success_response(data=result.model_dump())
            except json.JSONDecodeError:
                last_error = f"Provider returned invalid JSON from {models_url}"
            except Exception as exc:
                last_error = f"{type(exc).__name__}: {exc}"
            finally:
                if response is not None:
                    await response.aclose()

    result = ModelDiscoveryResult(
        success=False,
        normalized_api_url=normalized_api_url,
        error=last_error or "Unable to discover models from endpoint",
    )
    return success_response(data=result.model_dump())
