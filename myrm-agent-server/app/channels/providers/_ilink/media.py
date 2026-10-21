"""iLink media processing — inbound parsing and outbound upload.

Stateless helper functions for processing iLink media items:
- Inbound: parse image/voice/file/video items into MediaAttachment
- Outbound: prepare MessageItem from MediaAttachment, upload via CDN

[INPUT]

[OUTPUT]
- process_inbound_item: parse a MessageItem into text + media
- prepare_outbound_media: convert MediaAttachment → MessageItem for sending
- download_encrypted_media: download + decrypt CDN media to local path
- upload_media: encrypt + upload local file to CDN

[POS]
iLink media processing utility functions. Inbound parsing and outbound upload, zero state dependencies.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx

from app.channels.providers._ilink.crypto import (
    download_and_decrypt,
    encrypt_and_upload,
    generate_aes_key,
)
from app.channels.providers._ilink.silk import silk_to_wav
from app.channels.providers._ilink.types import (
    CDNMediaType,
    FileItem,
    ImageItem,
    ItemType,
    MediaInfo,
    MessageItem,
    VideoItem,
    VoiceItem,
)
from app.channels.types import (
    MediaAttachment,
    MediaType,
)

UploadUrlGetter = Callable[..., Awaitable[str]]

logger = logging.getLogger(__name__)

_temp_dir: Path | None = None


def _get_temp_dir() -> Path:
    global _temp_dir
    if _temp_dir is None or not _temp_dir.exists():
        _temp_dir = Path(tempfile.mkdtemp(prefix="wechat_media_"))
    return _temp_dir


def cleanup_temp_dir() -> None:
    """Remove the shared temp directory for iLink media files."""
    global _temp_dir
    if _temp_dir and _temp_dir.exists():
        shutil.rmtree(_temp_dir, ignore_errors=True)
        _temp_dir = None


# ── Inbound: parse iLink items ────────────────────────────────────────


async def process_inbound_item(
    item: MessageItem,
    text_parts: list[str],
    media_list: list[MediaAttachment],
    temp_files: set[Path],
    base_url: str,
    aes_http: httpx.AsyncClient,
) -> None:
    """Parse a single MessageItem, appending results to text_parts / media_list."""
    if item.type == ItemType.TEXT and item.text_item:
        text = item.text_item.text.strip()
        if text:
            text_parts.append(text)

    elif item.type == ItemType.IMAGE and item.image_item:
        await _process_image(item.image_item, media_list, temp_files, base_url, aes_http)

    elif item.type == ItemType.VOICE and item.voice_item:
        await _process_voice(item.voice_item, text_parts, media_list, temp_files, base_url, aes_http)

    elif item.type == ItemType.FILE and item.file_item:
        await _process_file(item.file_item, media_list, temp_files, base_url, aes_http)

    elif item.type == ItemType.VIDEO and item.video_item:
        await _process_video(item.video_item, media_list, temp_files, base_url, aes_http)


async def _process_image(
    img: ImageItem,
    media_list: list[MediaAttachment],
    temp_files: set[Path],
    base_url: str,
    http: httpx.AsyncClient,
) -> None:
    if img.url:
        media_list.append(MediaAttachment(media_type=MediaType.IMAGE, url=img.url))
    elif img.media:
        try:
            tmp_path = await download_encrypted_media(img.media, "image", temp_files, base_url, http)
            media_list.append(MediaAttachment(media_type=MediaType.IMAGE, path=str(tmp_path)))
        except Exception as exc:
            logger.warning("iLink media: image download failed: %s", exc)


async def _process_voice(
    voice: VoiceItem,
    text_parts: list[str],
    media_list: list[MediaAttachment],
    temp_files: set[Path],
    base_url: str,
    http: httpx.AsyncClient,
) -> None:
    if voice.text:
        text_parts.append(f"[Voice: {voice.text}]")
    elif voice.media:
        try:
            silk_path = await download_encrypted_media(voice.media, "voice", temp_files, base_url, http)
            wav_path = silk_path.with_suffix(".wav")
            if silk_to_wav(silk_path, wav_path):
                temp_files.add(wav_path)
                media_list.append(
                    MediaAttachment(
                        media_type=MediaType.AUDIO,
                        path=str(wav_path),
                        mime_type="audio/wav",
                    )
                )
            else:
                logger.warning("iLink media: SILK decode failed")
        except Exception as exc:
            logger.warning("iLink media: voice download failed: %s", exc)


async def _process_file(
    file_item: FileItem,
    media_list: list[MediaAttachment],
    temp_files: set[Path],
    base_url: str,
    http: httpx.AsyncClient,
) -> None:
    if file_item.media:
        try:
            tmp_path = await download_encrypted_media(file_item.media, "file", temp_files, base_url, http)
            media_list.append(
                MediaAttachment(
                    media_type=MediaType.DOCUMENT,
                    path=str(tmp_path),
                    filename=file_item.file_name,
                )
            )
        except Exception as exc:
            logger.warning("iLink media: file download failed: %s", exc)


async def _process_video(
    video: VideoItem,
    media_list: list[MediaAttachment],
    temp_files: set[Path],
    base_url: str,
    http: httpx.AsyncClient,
) -> None:
    if video.media:
        try:
            tmp_path = await download_encrypted_media(video.media, "video", temp_files, base_url, http)
            media_list.append(MediaAttachment(media_type=MediaType.VIDEO, path=str(tmp_path)))
        except Exception as exc:
            logger.warning("iLink media: video download failed: %s", exc)


# ── CDN download / upload ─────────────────────────────────────────────

_SUFFIX_MAP = {
    "image": ".jpg",
    "voice": ".silk",
    "video": ".mp4",
    "file": ".bin",
}


async def download_encrypted_media(
    media_info: MediaInfo,
    media_type: str,
    temp_files: set[Path],
    base_url: str,
    http: httpx.AsyncClient,
    temp_dir: Path | None = None,
) -> Path:
    """Download and decrypt CDN media to a temp file."""
    url = f"{base_url}/ilink/bot/download?{media_info.encrypt_query_param}"
    suffix = _SUFFIX_MAP.get(media_type, ".bin")

    if temp_dir is None:
        temp_dir = _get_temp_dir()

    tmp_path = temp_dir / f"{hashlib.sha256(url.encode()).hexdigest()[:16]}{suffix}"

    await download_and_decrypt(url, media_info.aes_key, tmp_path, http_client=http)
    temp_files.add(tmp_path)
    return tmp_path


# ── Outbound: prepare media items ─────────────────────────────────────


async def prepare_outbound_media(
    attachment: MediaAttachment,
    to_user_id: str,
    client_get_upload_url: UploadUrlGetter,
    http: httpx.AsyncClient,
) -> MessageItem | None:
    """Convert a MediaAttachment into a MessageItem for iLink API."""
    if attachment.media_type == MediaType.IMAGE:
        if attachment.url:
            return MessageItem(
                type=ItemType.IMAGE,
                image_item=ImageItem(url=attachment.url),
            )
        if attachment.path:
            media_info = await upload_media(
                Path(attachment.path),
                CDNMediaType.IMAGE,
                to_user_id,
                client_get_upload_url,
                http,
            )
            if media_info:
                return MessageItem(
                    type=ItemType.IMAGE,
                    image_item=ImageItem(media=media_info),
                )

    elif attachment.media_type == MediaType.VIDEO:
        if attachment.path:
            media_info = await upload_media(
                Path(attachment.path),
                CDNMediaType.VIDEO,
                to_user_id,
                client_get_upload_url,
                http,
            )
            if media_info:
                return MessageItem(
                    type=ItemType.VIDEO,
                    video_item=VideoItem(media=media_info),
                )

    elif attachment.media_type == MediaType.DOCUMENT:
        if attachment.path:
            media_info = await upload_media(
                Path(attachment.path),
                CDNMediaType.FILE,
                to_user_id,
                client_get_upload_url,
                http,
            )
            if media_info:
                return MessageItem(
                    type=ItemType.FILE,
                    file_item=FileItem(
                        media=media_info,
                        file_name=attachment.filename or Path(attachment.path).name,
                    ),
                )

    return None


async def upload_media(
    file_path: Path,
    media_type: CDNMediaType,
    to_user_id: str,
    client_get_upload_url: UploadUrlGetter,
    http: httpx.AsyncClient,
) -> MediaInfo | None:
    """Encrypt and upload a local file to iLink CDN."""
    if not file_path.exists():
        logger.warning("iLink media: file not found: %s", file_path)
        return None

    try:
        plaintext = file_path.read_bytes()
        raw_md5 = hashlib.md5(plaintext).hexdigest()
        aes_key = generate_aes_key()

        upload_url = await client_get_upload_url(
            to_user_id=to_user_id,
            media_type=media_type,
            file_size=len(plaintext),
            raw_file_md5=raw_md5,
            aes_key=aes_key,
        )

        await encrypt_and_upload(file_path, upload_url, aes_key, http_client=http)

        return MediaInfo(
            encrypt_query_param=(upload_url.split("?", 1)[1] if "?" in upload_url else ""),
            aes_key=aes_key,
        )
    except Exception as exc:
        logger.warning("iLink media: upload failed: %s", exc)
        return None
