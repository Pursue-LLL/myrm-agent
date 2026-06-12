from unittest.mock import AsyncMock, patch

import pytest
from httpx import Request, Response

from app.channels.core.exceptions import ChannelConnectionError
from app.channels.providers.imessage import IMessageChannel
from app.channels.types import ChannelStatus


def _server_info_response(private_api: bool = True) -> Response:
    """Create a mock BlueBubbles server/info response."""
    import json

    body = json.dumps({"status": 200, "data": {"private_api": private_api}}).encode()
    return Response(200, content=body, request=Request("GET", "http://localhost:1234/api/v1/server/info"))


@pytest.fixture
def imessage_channel():
    return IMessageChannel(api_url="http://localhost:1234", password="test")


@pytest.mark.asyncio
async def test_imessage_start_success(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _server_info_response(private_api=True)

        await imessage_channel.start()

        assert imessage_channel._status == ChannelStatus.RUNNING
        assert imessage_channel.is_connected
        assert imessage_channel._private_api_available is True
        mock_get.assert_called_once()


@pytest.mark.asyncio
async def test_imessage_start_retry_success(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # Fail twice, succeed on third
            mock_get.side_effect = [
                Exception("Connection refused"),
                Response(500, request=Request("GET", "http://localhost:1234/api/v1/server/info")),
                _server_info_response(private_api=False),
            ]

            await imessage_channel.start()

            assert imessage_channel._status == ChannelStatus.RUNNING
            assert imessage_channel.is_connected
            assert imessage_channel._private_api_available is False
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


# ── Typing Indicator Tests ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_start_typing_with_private_api(imessage_channel):
    imessage_channel._private_api_available = True
    with patch.object(imessage_channel._http, "post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Response(200, request=Request("POST", "http://x"))
        await imessage_channel.start_typing("iMessage;-;+15551234567")
        mock_post.assert_called_once()
        call_url = str(mock_post.call_args[0][0])
        assert "iMessage%3B-%3B%2B15551234567" in call_url


@pytest.mark.asyncio
async def test_start_typing_without_private_api(imessage_channel):
    imessage_channel._private_api_available = False
    with patch.object(imessage_channel._http, "post", new_callable=AsyncMock) as mock_post:
        await imessage_channel.start_typing("iMessage;-;+15551234567")
        mock_post.assert_not_called()


@pytest.mark.asyncio
async def test_stop_typing_with_private_api(imessage_channel):
    imessage_channel._private_api_available = True
    with patch.object(imessage_channel._http, "request", new_callable=AsyncMock) as mock_req:
        mock_req.return_value = Response(200, request=Request("DELETE", "http://x"))
        await imessage_channel.stop_typing("iMessage;-;+15551234567")
        mock_req.assert_called_once()
        assert mock_req.call_args[0][0] == "DELETE"
        call_url = str(mock_req.call_args[0][1])
        assert "iMessage%3B-%3B%2B15551234567" in call_url


@pytest.mark.asyncio
async def test_stop_typing_without_private_api(imessage_channel):
    imessage_channel._private_api_available = False
    with patch.object(imessage_channel._http, "request", new_callable=AsyncMock) as mock_req:
        await imessage_channel.stop_typing("iMessage;-;+15551234567")
        mock_req.assert_not_called()


@pytest.mark.asyncio
async def test_typing_graceful_on_failure(imessage_channel):
    """Typing failures should not propagate exceptions."""
    imessage_channel._private_api_available = True
    with patch.object(imessage_channel._http, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("Network error")
        await imessage_channel.start_typing("iMessage;-;+15551234567")


@pytest.mark.asyncio
async def test_private_api_detection_true(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _server_info_response(private_api=True)
        await imessage_channel.start()
        assert imessage_channel._private_api_available is True


@pytest.mark.asyncio
async def test_private_api_detection_false(imessage_channel):
    with patch.object(imessage_channel._http, "get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = _server_info_response(private_api=False)
        await imessage_channel.start()
        assert imessage_channel._private_api_available is False


@pytest.mark.asyncio
async def test_capabilities_typing_keepalive():
    ch = IMessageChannel(api_url="http://localhost:1234", password="test")
    assert ch.capabilities.typing_keepalive_interval == 55.0
