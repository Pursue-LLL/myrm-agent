"""The single entry point that turns image and video references into validated bytes.

[INPUT]
- core.security.http.secure_fetch::secure_get, ContentTooLargeError (POS: SSRF-protected outbound HTTP with a response size cap)
- core.security.guards.ssrf::SSRFSecurityError (POS: blocked outbound URL error)
- utils.mime_types::sniff_image_mime, is_video_content (POS: magic-bytes detection of image and video containers)

[OUTPUT]
- MediaInputPolicy: where references may be read from and how large the bytes may be
- MediaInputError: a reference that cannot become usable media bytes; the message names the offending field
- MediaLoader: injected async loader of one reference scheme (the business layer owns what ``media://`` means)
- resolve_media_inputs(): references -> validated bytes

[POS]
Image reference inputs and video reference inputs go through here and nowhere else, so every source is bounded the
same way: a reference is a loader scheme, a path inside the allowed roots, ``data:`` (images only) or http(s); its size
is checked before it is read in full; its leading bytes must be an image / video container (a ``.env`` or a key file
is refused here); the optional image hook runs once on the way out. Any reference that fails raises a
``MediaInputError`` naming it, so a caller never generates from fewer inputs than were asked for.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import httpx

from myrm_agent_harness.core.security.guards.ssrf import SSRFSecurityError
from myrm_agent_harness.core.security.http.secure_fetch import ContentTooLargeError, secure_get
from myrm_agent_harness.utils.mime_types import is_video_content, sniff_image_mime

MediaKind = Literal["image", "video"]
MediaLoader = Callable[[str], Awaitable[bytes]]
"""Loads one reference of a scheme: receives the text after ``scheme://`` and returns the bytes."""

_SCHEME = re.compile(r"^([A-Za-z][A-Za-z0-9+.-]+):(.*)$", re.DOTALL)  # two or more characters: ``C:\`` is a path
_IMAGE_TIMEOUT_S = 30.0
_VIDEO_TIMEOUT_S = 60.0


class MediaInputError(ValueError):
    """A media reference could not be turned into usable bytes."""


@dataclass(frozen=True, slots=True)
class MediaInputPolicy:
    """What a caller allows its references to touch."""

    allowed_roots: tuple[Path, ...] = ()
    """Directories file references may be read from; a relative path is looked up under each in turn."""
    allow_private_networks: bool = False
    """Local deployments may fetch from private addresses; everywhere else http(s) goes through SSRF protection."""
    loaders: Mapping[str, MediaLoader] = field(default_factory=dict)
    """Scheme (lower case, no ``://``) -> loader."""
    image_hook: Callable[[bytes], bytes] | None = None
    """Applied once to every resolved image (size and format normalisation)."""
    max_image_bytes: int = 20 * 1024 * 1024
    max_video_bytes: int = 100 * 1024 * 1024


async def resolve_media_inputs(
    refs: Sequence[str],
    kind: MediaKind,
    policy: MediaInputPolicy,
    *,
    field_name: str,
) -> list[bytes]:
    """Resolve every reference to validated bytes, in order.

    Raises:
        MediaInputError: A reference is empty, unsupported, outside the allowed roots, too large, unreachable or not
            an image / video; the message starts with ``field_name`` (indexed when there are several references).
    """
    resolved: list[bytes] = []
    for index, ref in enumerate(refs):
        where = field_name if len(refs) == 1 else f"{field_name}[{index}]"
        try:
            data = await _load(ref.strip(), kind, policy)
            _validate(data, kind)
        except MediaInputError as exc:
            raise MediaInputError(f"{where}: {exc}") from None
        resolved.append(policy.image_hook(data) if kind == "image" and policy.image_hook else data)
    return resolved


async def _load(ref: str, kind: MediaKind, policy: MediaInputPolicy) -> bytes:
    if not ref:
        raise MediaInputError("reference is empty")
    limit = policy.max_image_bytes if kind == "image" else policy.max_video_bytes
    match = _SCHEME.match(ref)
    if match is None:
        return await asyncio.to_thread(_read_path, ref, policy.allowed_roots, limit)
    scheme, rest = match.group(1).lower(), match.group(2)
    if scheme in policy.loaders:
        return await _run_loader(policy.loaders[scheme], rest.removeprefix("//"), limit)
    if scheme == "data":
        if kind != "image":
            raise MediaInputError("data: references are accepted for images only")
        return _decode_data_url(rest, limit)
    if scheme in ("http", "https"):
        timeout = _IMAGE_TIMEOUT_S if kind == "image" else _VIDEO_TIMEOUT_S
        return await _fetch(ref, policy.allow_private_networks, limit, timeout)
    raise MediaInputError(
        f"unsupported reference '{scheme}:'; use a media:// reference, a workspace path, data: (images) or http(s)"
    )


def _validate(data: bytes, kind: MediaKind) -> None:
    if not data:
        raise MediaInputError("the reference resolved to no data")
    if kind == "image" and sniff_image_mime(data) is None:
        raise MediaInputError("not a supported image (png, jpeg, webp, gif or bmp)")
    if kind == "video" and not is_video_content(data):
        raise MediaInputError("not a supported video (mp4, mov, webm or avi)")


def _too_large(limit: int) -> MediaInputError:
    return MediaInputError(f"larger than the {limit // (1024 * 1024)} MB limit")


async def _run_loader(loader: MediaLoader, ref: str, limit: int) -> bytes:
    try:
        data = await loader(ref)
    except (OSError, LookupError) as exc:
        raise MediaInputError("not found") from exc
    if len(data) > limit:
        raise _too_large(limit)
    return data


def _read_path(ref: str, allowed_roots: Sequence[Path], limit: int) -> bytes:
    roots = [root.resolve() for root in allowed_roots if root.is_dir()]
    path = Path(ref)
    candidates = [path] if path.is_absolute() else [root / path for root in roots]
    for candidate in candidates:
        try:
            resolved = candidate.resolve(strict=True)
        except (OSError, RuntimeError):
            continue  # a missing candidate under one root may still exist under the next
        if not any(resolved.is_relative_to(root) for root in roots):
            raise MediaInputError("path is outside the folders this agent may read")
        if not resolved.is_file():
            continue
        if resolved.stat().st_size > limit:
            raise _too_large(limit)
        return resolved.read_bytes()
    raise MediaInputError("file not found")


def _decode_data_url(rest: str, limit: int) -> bytes:
    header, comma, payload = rest.partition(",")
    if not comma or "base64" not in header.lower():
        raise MediaInputError("data: references must be base64 encoded")
    if len(payload) * 3 // 4 > limit:
        raise _too_large(limit)
    try:
        return base64.b64decode(payload, validate=True)
    except binascii.Error:
        raise MediaInputError("invalid base64 data") from None


async def _fetch(url: str, allow_private_networks: bool, limit: int, timeout: float) -> bytes:
    try:
        response = await secure_get(
            url,
            timeout=timeout,
            enable_ssrf_shield=not allow_private_networks,
            max_content_length=limit,
        )
        response.raise_for_status()
        return response.content
    except ContentTooLargeError:
        raise _too_large(limit) from None
    except SSRFSecurityError:
        raise MediaInputError("address is blocked by the network policy") from None
    except (httpx.HTTPError, httpx.InvalidURL) as exc:
        raise MediaInputError(f"download failed ({type(exc).__name__})") from None
