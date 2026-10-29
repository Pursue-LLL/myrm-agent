"""Tests for how Zalo's upload classifies a transport error: retriable only when the request never left."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.channels.core.exceptions import ChannelSendError
from app.channels.providers.zalo import ZaloChannel
from app.channels.types import MediaAttachment, MediaType


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error", "retriable"),
    [
        (httpx.ConnectError("down"), True),
        (httpx.ReadTimeout("slow"), False),
    ],
)
async def test_upload_transport_error_is_retriable_only_when_the_request_never_left(
    tmp_path: Path, error: httpx.RequestError, retriable: bool
) -> None:
    photo = tmp_path / "photo.jpg"
    photo.write_bytes(b"imgdata")
    channel = ZaloChannel(access_token="tok123")
    channel._http = AsyncMock()
    channel._http.post = AsyncMock(side_effect=error)

    with pytest.raises(ChannelSendError) as excinfo:
        await channel._upload_media(MediaAttachment(path=str(photo), media_type=MediaType.IMAGE))

    assert excinfo.value.retriable is retriable
