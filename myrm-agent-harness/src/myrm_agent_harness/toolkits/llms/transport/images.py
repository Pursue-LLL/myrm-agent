"""Image generation and editing calls: OpenAI-family ``/images``, Gemini, Stability and MiniMax image-01.

[INPUT]
- transport.service_routes (POS: service_route — provider, endpoint and credential)
- transport.openai_chat (POS: openai_endpoint — URL and auth headers of an OpenAI-family path)
- transport.http (POS: PreparedRequest, asend_json — JSON and multipart round trips)
- utils.mime_types (POS: detect_image_mime, extension_for_mime for uploaded images)

[OUTPUT]
- GeneratedImage: one returned image (URL or base64) and the prompt the provider actually used
- ImageProviderError: a provider refusal that arrives inside an HTTP 200 answer, with the status it stands for
- agenerate_images / aedit_images: the images of one generation / edit call

[POS]
Each provider family has its own request shape and answer shape, so each gets a builder/parser pair here and the
call is one ``asend_json``. The OpenAI family (OpenAI, Azure deployments, xAI, Together, Volcengine and any
compatible gateway) shares ``/images/generations`` and ``/images/edits``; Gemini serves Imagen through ``:predict``
and its image models through ``:generateContent``; Stability takes multipart forms; MiniMax image-01 has its own
JSON endpoint. Editing exists only on the OpenAI family. Transport failures surface as ``LLMHTTPError`` so the
image generator decides retries from the status code instead of exception class names.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

from myrm_agent_harness.toolkits.llms.transport.http import FilePart, PreparedRequest, asend_json
from myrm_agent_harness.toolkits.llms.transport.openai_chat import openai_endpoint
from myrm_agent_harness.toolkits.llms.transport.params import split_params
from myrm_agent_harness.toolkits.llms.transport.profile import Route, UnsupportedProviderError
from myrm_agent_harness.toolkits.llms.transport.service_routes import service_route
from myrm_agent_harness.utils.mime_types import detect_image_mime, extension_for_mime

_OPENAI_WIRES: Final = frozenset({"openai_chat", "azure_openai"})
_NON_OPENAI_IMAGE_PROVIDERS: Final = frozenset({"stability", "minimax_image"})
# Azure serves its image deployments on a newer API version than its chat default.
_AZURE_IMAGE_API_VERSION: Final = "2025-02-01-preview"

# Model names the settings offer that name a model family instead of a provider-qualified id.
_ALIASES: Final = {
    "flux/schnell": "together_ai/black-forest-labs/FLUX.1-schnell",
    "flux/pro": "together_ai/black-forest-labs/FLUX.1.1-pro",
}


def _ratios(*names: str) -> dict[str, float]:
    return {name: int(w) / int(h) for name in names for w, h in [name.split(":")]}


_GEMINI_RATIOS: Final = _ratios(
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3", "4:5", "5:4", "8:1", "9:16", "16:9", "21:9"
)
_STABILITY_RATIOS: Final = _ratios("1:1", "16:9", "9:16", "4:3", "3:4", "21:9", "9:21", "3:2", "2:3", "5:4", "4:5")
_STABILITY_DEFAULT_ENDPOINT: Final = "/v2beta/stable-image/generate/sd3"
# First match wins: the key is looked up inside the model id, so "sd3.5-large-turbo" resolves through "sd3".
_STABILITY_ENDPOINTS: Final = {
    "sd3": _STABILITY_DEFAULT_ENDPOINT,
    "stable-image-ultra": "/v2beta/stable-image/generate/ultra",
    "stable-image-core": "/v2beta/stable-image/generate/core",
}
_MINIMAX_RATIOS: Final = frozenset({"1:1", "16:9", "4:3", "3:2", "2:3", "3:4", "9:16", "21:9"})
_MINIMAX_SIZES: Final = {
    "1024x1024": "1:1",
    "1280x720": "16:9",
    "1152x864": "4:3",
    "1248x832": "3:2",
    "832x1248": "2:3",
    "864x1152": "3:4",
    "720x1280": "9:16",
    "1344x576": "21:9",
}
# MiniMax answers 200 with its own status code in ``base_resp``; these are the HTTP statuses they stand for.
_MINIMAX_STATUS: Final = {1002: 429, 1004: 401, 1008: 402, 1026: 400, 2013: 400, 2049: 401}


@dataclass(frozen=True, slots=True)
class GeneratedImage:
    """One image a provider returned: a URL or inline base64 data."""

    url: str | None = None
    b64_json: str | None = None
    revised_prompt: str | None = None


class ImageProviderError(Exception):
    """A provider refused an image request inside a successful HTTP answer."""

    def __init__(self, provider: str, status_code: int, message: str) -> None:
        self.llm_provider = provider
        self.status_code = status_code
        super().__init__(f"{provider} image error: {message}")


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _dimensions(size: str) -> tuple[int, int] | None:
    width, separator, height = size.lower().partition("x")
    if not separator or not width.isdigit() or not height.isdigit() or int(width) == 0 or int(height) == 0:
        return None
    return int(width), int(height)


def _nearest_ratio(size: str, ratios: Mapping[str, float]) -> str | None:
    """The supported aspect ratio for ``size``: a ratio given as ``W:H`` as-is, ``WxH`` snapped to the closest."""
    if size in ratios:
        return size
    dims = _dimensions(size)
    if dims is None:
        return None
    wanted = dims[0] / dims[1]
    return min(ratios, key=lambda name: abs(math.log(ratios[name] / wanted)))


def _route(model: str, api_key: str | None, api_base: str | None) -> Route:
    return service_route(_ALIASES.get(model.lower(), model), api_key=api_key, api_base=api_base)


def _nonempty(images: list[GeneratedImage], provider: str) -> list[GeneratedImage]:
    if not images:
        raise ValueError(f"{provider} returned no image")
    return images


# --- OpenAI family -------------------------------------------------------------------------------------------


def _openai_generation(
    route: Route, prompt: str, size: str, quality: str | None, style: str | None, n: int, timeout: float
) -> PreparedRequest:
    url, query, headers = openai_endpoint(
        route, split_params({"api_version": _AZURE_IMAGE_API_VERSION}), "/images/generations"
    )
    body: dict[str, object] = {"prompt": prompt, "n": n, "size": size}
    if route.profile.wire != "azure_openai":  # an Azure deployment is addressed by the URL
        body["model"] = route.model
    if quality:
        body["quality"] = quality
    if style:
        body["style"] = style
    return PreparedRequest(provider=route.profile.id, url=url, headers=headers, body=body, timeout=timeout, query=query)


def _openai_edit(
    route: Route, image: bytes, prompt: str, mask: bytes | None, size: str, n: int, timeout: float
) -> PreparedRequest:
    url, query, headers = openai_endpoint(
        route, split_params({"api_version": _AZURE_IMAGE_API_VERSION}), "/images/edits"
    )
    form = {"prompt": prompt, "n": str(n), "size": size}
    if route.profile.wire != "azure_openai":
        form["model"] = route.model
    # dall-e-2 takes a single `image`; the GPT image models take a list under `image[]`.
    files: dict[str, FilePart] = {"image" if route.model == "dall-e-2" else "image[]": _upload("image", image)}
    if mask is not None:
        files["mask"] = _upload("mask", mask)
    return PreparedRequest(
        provider=route.profile.id,
        url=url,
        headers=headers,
        body=None,
        timeout=timeout,
        query=query,
        form=form,
        files=files,
    )


def _upload(name: str, data: bytes) -> tuple[str, bytes, str]:
    mime = detect_image_mime(data)
    return f"{name}.{extension_for_mime(mime)}", data, mime


def _parse_openai(payload: dict[str, object], provider: str) -> list[GeneratedImage]:
    data = payload.get("data")
    items = [d for d in data if isinstance(d, dict)] if isinstance(data, list) else []
    return _nonempty(
        [
            GeneratedImage(
                url=_text(d.get("url")),
                b64_json=_text(d.get("b64_json")),
                revised_prompt=_text(d.get("revised_prompt")),
            )
            for d in items
        ],
        provider,
    )


# --- Gemini --------------------------------------------------------------------------------------------------


def _gemini_image_size(width: int, height: int) -> str:
    side = math.sqrt(width * height)
    if side < 768:
        return "512"
    if side < 1536:
        return "1K"
    if side < 3072:
        return "2K"
    return "4K"


def _gemini_request(route: Route, prompt: str, size: str, n: int, timeout: float) -> PreparedRequest:
    ratio = _nearest_ratio(size, _GEMINI_RATIOS)
    dims = _dimensions(size)
    # 1K is every model's default, and Imagen 3 does not document the field: send it only when it changes the output.
    image_size = _gemini_image_size(*dims) if dims else None
    if image_size == "1K":
        image_size = None
    headers = {"x-goog-api-key": route.api_key} if route.api_key else {}
    base = f"{route.base_url}/models/{route.model}"
    if "gemini" in route.model:  # Gemini image models answer through generateContent
        image_config: dict[str, object] = {}
        if ratio:
            image_config["aspectRatio"] = ratio
        if image_size and "2.5-flash" not in route.model:  # 2.5 Flash Image has a fixed output size
            image_config["imageSize"] = image_size
        config: dict[str, object] = {"response_modalities": ["IMAGE", "TEXT"], "candidateCount": n}
        if image_config:
            config["imageConfig"] = image_config
        body: dict[str, object] = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
        url = f"{base}:generateContent"
    else:
        parameters: dict[str, object] = {"sampleCount": n}
        if ratio:
            parameters["aspectRatio"] = ratio
        if image_size:
            parameters["imageSize"] = image_size
        body = {"instances": [{"prompt": prompt}], "parameters": parameters}
        url = f"{base}:predict"
    return PreparedRequest(provider="gemini", url=url, headers=headers, body=body, timeout=timeout)


def _parse_gemini(payload: dict[str, object], model: str) -> list[GeneratedImage]:
    images: list[GeneratedImage] = []
    if "gemini" in model:
        for candidate in _dicts(payload.get("candidates")):
            content = candidate.get("content")
            for part in _dicts(content.get("parts") if isinstance(content, dict) else None):
                inline = part.get("inlineData")
                if isinstance(inline, dict) and (data := _text(inline.get("data"))):
                    images.append(GeneratedImage(b64_json=data))
    else:
        images = [
            GeneratedImage(b64_json=data)
            for prediction in _dicts(payload.get("predictions"))
            if (data := _text(prediction.get("bytesBase64Encoded")))
        ]
    return _nonempty(images, "gemini")


def _dicts(value: object) -> list[dict[str, object]]:
    return [v for v in value if isinstance(v, dict)] if isinstance(value, list) else []


# --- Stability -----------------------------------------------------------------------------------------------


def _stability_request(route: Route, prompt: str, size: str, timeout: float) -> PreparedRequest:
    model = route.model.lower()
    endpoint = next((ep for key, ep in _STABILITY_ENDPOINTS.items() if key in model), _STABILITY_DEFAULT_ENDPOINT)
    form = {"prompt": prompt, "output_format": "png"}
    if ratio := _nearest_ratio(size, _STABILITY_RATIOS):
        form["aspect_ratio"] = ratio
    headers = {"Accept": "application/json"}
    if route.api_key:
        headers["Authorization"] = f"Bearer {route.api_key}"
    return PreparedRequest(
        provider="stability",
        url=f"{route.base_url}{endpoint}",
        headers=headers,
        body=None,
        timeout=timeout,
        form=form,
        files={"none": ""},  # Stability only accepts multipart; the empty file field forces that encoding
    )


def _parse_stability(payload: dict[str, object]) -> list[GeneratedImage]:
    if payload.get("errors"):
        raise ImageProviderError("stability", 400, str(payload["errors"]))
    if payload.get("finish_reason") == "CONTENT_FILTERED":
        raise ImageProviderError("stability", 400, "content was filtered by the safety system")
    image = _text(payload.get("image"))
    return _nonempty([GeneratedImage(b64_json=image)] if image else [], "stability")


# --- MiniMax image-01 ----------------------------------------------------------------------------------------


def _minimax_request(route: Route, prompt: str, size: str, n: int, timeout: float) -> PreparedRequest:
    ratio = size if size in _MINIMAX_RATIOS else _MINIMAX_SIZES.get(size, "1:1")
    body: dict[str, object] = {
        "model": route.model,
        "prompt": prompt,
        "aspect_ratio": ratio,
        "response_format": "url",
    }
    if n > 1:
        body["n"] = n
    headers = {"Authorization": f"Bearer {route.api_key}"} if route.api_key else {}
    return PreparedRequest(
        provider="minimax_image",
        url=f"{route.base_url}/v1/image_generation",
        headers=headers,
        body=body,
        timeout=timeout,
    )


def _parse_minimax(payload: dict[str, object]) -> list[GeneratedImage]:
    base = payload.get("base_resp")
    status = base.get("status_code") if isinstance(base, dict) else None
    if status != 0:
        message = base.get("status_msg", "unknown") if isinstance(base, dict) else "unknown"
        raise ImageProviderError(
            "minimax_image",
            _MINIMAX_STATUS.get(status, 500) if isinstance(status, int) else 500,
            f"{status}: {message}",
        )
    data = payload.get("data")
    result = data if isinstance(data, dict) else {}
    urls = result.get("image_urls")
    encoded = result.get("image_base64")
    images = [GeneratedImage(url=u) for u in urls if isinstance(u, str)] if isinstance(urls, list) else []
    images += [GeneratedImage(b64_json=b) for b in encoded if isinstance(b, str)] if isinstance(encoded, list) else []
    return _nonempty(images, "minimax_image")


# --- entry points --------------------------------------------------------------------------------------------


async def agenerate_images(
    model: str,
    prompt: str,
    *,
    size: str,
    quality: str | None,
    style: str | None,
    n: int,
    api_key: str | None,
    api_base: str | None,
    timeout: float,
) -> list[GeneratedImage]:
    """The images one text-to-image call returns (at least one)."""
    route = _route(model, api_key, api_base)
    provider = route.profile.id
    # Stability and MiniMax profiles carry the default wire, so their own shapes are matched first.
    if provider == "stability":
        return _parse_stability(await asend_json(_stability_request(route, prompt, size, timeout)))
    if provider == "minimax_image":
        return _parse_minimax(await asend_json(_minimax_request(route, prompt, size, n, timeout)))
    if route.profile.wire in _OPENAI_WIRES:
        payload = await asend_json(_openai_generation(route, prompt, size, quality, style, n, timeout))
        return _parse_openai(payload, provider)
    if route.profile.wire == "gemini":
        payload = await asend_json(_gemini_request(route, prompt, size, n, timeout))
        return _parse_gemini(payload, route.model)
    raise UnsupportedProviderError(f"Provider '{provider}' has no image generation endpoint")


async def aedit_images(
    model: str,
    image: bytes,
    prompt: str,
    *,
    mask: bytes | None,
    size: str,
    n: int,
    api_key: str | None,
    api_base: str | None,
    timeout: float,
) -> list[GeneratedImage]:
    """The images one image-edit call returns (at least one); only the OpenAI family edits."""
    route = _route(model, api_key, api_base)
    if route.profile.wire not in _OPENAI_WIRES or route.profile.id in _NON_OPENAI_IMAGE_PROVIDERS:
        raise UnsupportedProviderError(f"Provider '{route.profile.id}' has no image editing endpoint")
    payload = await asend_json(_openai_edit(route, image, prompt, mask, size, n, timeout))
    return _parse_openai(payload, route.profile.id)
