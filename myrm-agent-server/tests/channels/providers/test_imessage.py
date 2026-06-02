from unittest.mock import AsyncMock, patch

import pytest
from httpx import Request, Response

from app.channels.core.exceptions import ChannelConnectionError
from app.channels.providers.imessage import IMessageChannel
from app.channels.types import ChannelStatus


@pytest.fixture
def imessage_channel():
    return IMessageChannel(api_url="http://localhost:1234", password="test")


@pytest.mark.asyncio
async def test_imessage_start_success(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, request=Request("GET", "http://localhost:1234/api/v1/server/info"))

        await imessage_channel.start()

        assert imessage_channel._status == ChannelStatus.RUNNING
        assert imessage_channel.is_connected
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_imessage_start_retry_success(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Fail twice, succeed on third
            mock_get.side_effect = [
                Exception("Connection refused"),
                Response(500, request=Request("GET", "http://localhost:1234/api/v1/server/info")),
                Response(200, request=Request("GET", "http://localhost:1234/api/v1/server/info")),
            ]

            await imessage_channel.start()

            assert imessage_channel._status == ChannelStatus.RUNNING
            assert imessage_channel.is_connected
            assert mock_get.call_count == 3
            assert mock_sleep.call_count == 2


@pytest.mark.asyncio
async def test_imessage_start_failure_raises_error(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Always fail
            mock_get.side_effect = Exception("Connection refused")

            with pytest.raises(ChannelConnectionError):
                await imessage_channel.start()

            assert imessage_channel._status == ChannelStatus.DEGRADED
            assert not imessage_channel.is_connected
            assert mock_get.call_count == 5
            assert mock_sleep.call_count == 4
