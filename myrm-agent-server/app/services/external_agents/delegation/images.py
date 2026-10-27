"""Put the images of a delegated turn where the external CLI can read them.

[INPUT]
- app.config.settings::settings (POS: 状态目录 settings.database.state_dir)
- app.core.utils.files_utils::read_image_bytes (POS: 存储 URL → 图片原始字节，只读本地存储)
- app.services.external_agents.delegation.prompt::image_url, is_video (POS: 图片内容块的 URL 取法与视频判别)

[OUTPUT]
- staging_dir: 暂存目录（状态目录下的固定路径）
- stage_images: 用户回合里的图片 → 暂存目录里的本地文件，回合结束后删除
- StagedImages: 图片块已指向暂存文件的用户回合，与暂存文件的路径

[POS]
外部 CLI 不认本服务的图片来源。Web 模式里图片是本服务的存储 URL（Claude 的 `Read` 一个 http 地址得到
File does not exist），Tauri 里是任意位置的 `file://`（Claude 的 `Read` 默认只到工作目录）。
这里把存储 URL、`file://`、data URL 三种来源的图片校验后落成状态目录下的一个私有文件，并把图片块改指向它，
提示词里的路径一行与交给 CLI 的文件因此是同一个：能收图的 CLI
（Claude、Codex）由 harness 按各自的方式带上这张图，收不了图的后端仍有这一行路径。文件在回合之后删除（调用方在
上下文里以 `aclosing` 跑回合流，上下文退出时 CLI 已停止）；服务中途退出遗留的文件由之后的暂存清掉。任何一张图落盘
失败都只记一条 WARNING 并保持原样，不让回合失败；外部 http(s) 地址从不被抓取。
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import logging
import os
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeGuard
from urllib.parse import urlparse
from urllib.request import url2pathname
from uuid import uuid4

from app.config.settings import settings
from app.core.utils.files_utils import read_image_bytes
from app.services.external_agents.delegation.prompt import image_url, is_video

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

logger = logging.getLogger(__name__)

# The per-image limit of the models behind the CLIs; a larger file stays the prompt's path line.
MAX_IMAGE_BYTES = 5 * 1024 * 1024
# A file a stopped server left behind is removed by the first staging after this long.
_STALE_AFTER_SECONDS = 24 * 60 * 60
_DIRECTORY_NAME = "delegation-images"


class _NotStaged(Exception):
    """An image that stays as the prompt's path line; the message says why (never the URL or the bytes)."""


@dataclass(frozen=True, slots=True)
class StagedImages:
    """The user turn with every staged image pointing at its file, and those files in order."""

    query: object
    paths: list[str]


def staging_dir() -> Path:
    """The directory staged images live in: the same path for every turn and chat."""
    return Path(settings.database.state_dir) / _DIRECTORY_NAME


def _extension(data: bytes) -> str | None:
    """The file extension of the image formats the CLIs take, from the bytes themselves (a name proves nothing)."""
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _is_stageable(part: object) -> TypeGuard[dict[str, object]]:
    """An image block with a URL; a video is never staged."""
    return isinstance(part, dict) and part.get("type") == "image_url" and not is_video(part) and image_url(part) is not None


def _decode_data_url(url: str) -> bytes:
    header, _, payload = url.partition(",")
    if not header.endswith(";base64"):
        raise _NotStaged("unsupported_data_url")
    if len(payload) > MAX_IMAGE_BYTES * 4 // 3 + 4:
        raise _NotStaged("too_large")
    try:
        return base64.b64decode(payload, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise _NotStaged("invalid_data_url") from exc


def _read_local_file(path: str) -> bytes:
    with open(path, "rb") as handle:
        return handle.read(MAX_IMAGE_BYTES + 1)


async def _read(url: str) -> bytes:
    """The bytes behind ``url``: a data URL, a local file, or a file of this server's own storage."""
    if url.startswith("data:"):
        return _decode_data_url(url)
    if url.startswith("file:"):
        try:
            return await asyncio.to_thread(_read_local_file, url2pathname(urlparse(url).path))
        except OSError as exc:
            raise _NotStaged("unreadable_file") from exc
    try:
        content, _ = await read_image_bytes(url)
    except FileNotFoundError as exc:
        # Not one of ours (an external address) or already gone; nothing is ever fetched over the network.
        raise _NotStaged("not_in_storage") from exc
    return content


def _prepare(directory: Path) -> None:
    """Make sure the directory exists (private to the user) and drop what an earlier run left in it."""
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    cutoff = time.time() - _STALE_AFTER_SECONDS
    with os.scandir(directory) as entries:
        for entry in entries:
            try:
                if entry.is_file(follow_symlinks=False) and entry.stat(follow_symlinks=False).st_mtime < cutoff:
                    os.unlink(entry.path)
            except OSError:
                logger.debug("delegation_image_sweep_failed", exc_info=True)


def _write(directory: Path, data: bytes, extension: str) -> Path:
    path = directory / f"{uuid4().hex}.{extension}"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as handle:
        handle.write(data)
    return path


def _remove(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("delegation_image_remove_failed", exc_info=True)


async def _stage(part: dict[str, object], directory: Path) -> Path:
    url = image_url(part)
    if url is None:
        raise _NotStaged("no_url")
    data = await _read(url)
    if len(data) > MAX_IMAGE_BYTES:
        raise _NotStaged("too_large")
    extension = _extension(data)
    if extension is None:
        raise _NotStaged("not_an_image")
    return await asyncio.to_thread(_write, directory, data, extension)


async def _staged_part(part: dict[str, object], directory: Path, staged: list[Path]) -> dict[str, object]:
    """``part`` pointing at its staged file, or ``part`` itself when the image could not be staged."""
    try:
        path = await _stage(part, directory)
    except _NotStaged as exc:
        logger.warning("delegation_image_not_staged reason=%s", exc)
        return part
    except Exception as exc:
        # Staging is a convenience for the CLI; whatever went wrong, the turn still runs with the path line.
        logger.warning("delegation_image_not_staged reason=error:%s", type(exc).__name__)
        return part
    staged.append(path)
    return {**part, "image_url": {"url": path.as_uri()}}


@asynccontextmanager
async def stage_images(query: object, *, directory: Path | None = None) -> AsyncIterator[StagedImages]:
    """The turn ``query`` with its images staged for the CLI; the files are removed when the context exits.

    A turn without images touches nothing on disk. Exit the context only after the CLI turn has stopped.
    """
    if not isinstance(query, list) or not any(_is_stageable(part) for part in query):
        yield StagedImages(query, [])
        return
    target = directory if directory is not None else staging_dir()
    try:
        await asyncio.to_thread(_prepare, target)
    except OSError as exc:
        logger.warning("delegation_image_dir_unavailable error=%s", type(exc).__name__)
        yield StagedImages(query, [])
        return

    staged: list[Path] = []
    try:
        parts = [await _staged_part(part, target, staged) if _is_stageable(part) else part for part in query]
        if staged:
            logger.info("delegation_images_staged count=%d", len(staged))
        yield StagedImages(parts, [str(path) for path in staged])
    finally:
        if staged:
            # Shielded: a cancelled turn must still leave nothing behind.
            await asyncio.shield(asyncio.to_thread(_remove, staged))
