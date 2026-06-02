"""Tests for async login protocol and helpers.

Tests Protocol types, QRCodeLoginHelper, and OAuth2LoginHelper.
"""

import asyncio
import base64
import time
from dataclasses import FrozenInstanceError

import pytest

from app.channels.core.exceptions import ChannelAuthError
from app.channels.helpers import (
    OAuth2LoginHelper,
    QRCodeLoginHelper,
)
from app.channels.protocols import (
    LoginEvent,
    LoginMethod,
    LoginState,
    LoginStatus,
)


class TestAsyncLoginTypes:
    """Test AsyncLoginProtocol types."""

    def test_login_method_enum(self):
        """Test LoginMethod enum values."""
        assert LoginMethod.QR_CODE.value == "qr_code"
        assert LoginMethod.OAUTH2.value == "oauth2"
        assert LoginMethod.API_TOKEN.value == "api_token"
        assert LoginMethod.PASSWORD.value == "password"
        assert LoginMethod.SSO.value == "sso"

    def test_login_status_enum(self):
        """Test LoginStatus enum values."""
        assert LoginStatus.IDLE.value == "idle"
        assert LoginStatus.GENERATING.value == "generating"
        assert LoginStatus.WAITING_USER_ACTION.value == "waiting"
        assert LoginStatus.SUCCESS.value == "success"
        assert LoginStatus.FAILED.value == "failed"

    def test_login_state_frozen(self):
        """Test LoginState is frozen (immutable)."""
        state = LoginState(
            status=LoginStatus.IDLE,
            method=LoginMethod.QR_CODE,
        )
        with pytest.raises(FrozenInstanceError):
            state.status = LoginStatus.SUCCESS

    def test_login_event_creation(self):
        """Test LoginEvent creation."""
        state = LoginState(
            status=LoginStatus.SUCCESS,
            method=LoginMethod.QR_CODE,
            progress_percent=100,
        )
        event = LoginEvent(
            timestamp=time.time(),
            state=state,
            channel_name="wechat",
            credentials={"bot_token": "xxx"},
        )
        assert event.state.status == LoginStatus.SUCCESS
        assert event.channel_name == "wechat"
        assert event.credentials == {"bot_token": "xxx"}


class TestQRCodeLoginHelper:
    """Test QRCodeLoginHelper."""

    async def mock_fetch_qr(self) -> tuple[str, bytes]:
        """Mock QR code fetch."""
        qr_id = "qr123"
        qr_image = base64.b64encode(b"fake-qr-image")
        return qr_id, base64.b64decode(qr_image)

    async def mock_poll_success(self, qr_id: str) -> dict[str, str] | None:
        """Mock successful QR scan."""
        await asyncio.sleep(0.1)
        return {"bot_token": "xxx", "user_id": "yyy"}

    async def mock_poll_pending(self, qr_id: str) -> dict[str, str] | None:
        """Mock pending QR scan."""
        return None

    @pytest.mark.asyncio
    async def test_qr_login_success(self):
        """Test successful QR login flow."""
        helper = QRCodeLoginHelper(
            fetch_qr_fn=self.mock_fetch_qr,
            poll_status_fn=self.mock_poll_success,
            qr_ttl=1.0,
            poll_interval=0.05,
        )

        events = []
        async for event in helper.run(timeout=2.0, channel_name="test"):
            events.append(event)

        assert len(events) == 3
        assert events[0].state.status == LoginStatus.GENERATING
        assert events[1].state.status == LoginStatus.WAITING_USER_ACTION
        assert events[1].state.qr_code_base64 is not None
        assert events[2].state.status == LoginStatus.SUCCESS
        assert events[2].credentials is not None

    @pytest.mark.asyncio
    async def test_qr_login_timeout(self):
        """Test QR login timeout."""
        helper = QRCodeLoginHelper(
            fetch_qr_fn=self.mock_fetch_qr,
            poll_status_fn=self.mock_poll_pending,
            qr_ttl=0.2,
            poll_interval=0.05,
            max_refresh=0,
        )

        events = []
        with pytest.raises(TimeoutError):
            async for event in helper.run(timeout=0.5, channel_name="test"):
                events.append(event)

        assert any(e.state.status == LoginStatus.TIMEOUT for e in events)

    @pytest.mark.asyncio
    async def test_qr_login_cancel(self):
        """Test QR login cancellation."""
        helper = QRCodeLoginHelper(
            fetch_qr_fn=self.mock_fetch_qr,
            poll_status_fn=self.mock_poll_pending,
            qr_ttl=10.0,
            poll_interval=0.1,
        )

        events = []

        async def cancel_after_delay():
            await asyncio.sleep(0.2)
            helper.cancel()

        asyncio.create_task(cancel_after_delay())

        async for event in helper.run(timeout=5.0, channel_name="test"):
            events.append(event)

        assert any(e.state.status == LoginStatus.CANCELLED for e in events)


class TestOAuth2LoginHelper:
    """Test OAuth2LoginHelper."""

    async def mock_token_exchange(self, code: str, state: str) -> dict[str, str]:
        """Mock OAuth2 token exchange."""
        return {"access_token": "xxx", "refresh_token": "yyy"}

    @pytest.mark.asyncio
    async def test_oauth2_login_success(self):
        """Test successful OAuth2 login flow with correct CSRF state."""
        helper = OAuth2LoginHelper(
            authorization_endpoint="https://auth.example.com/oauth/authorize",
            token_endpoint="https://auth.example.com/oauth/token",
            client_id="client123",
            client_secret="secret456",
            scope=["read", "write"],
            callback_handler=self.mock_token_exchange,
        )

        events: list[LoginEvent] = []

        async def simulate_callback():
            while helper._csrf_state is None:
                await asyncio.sleep(0.05)
            await helper.handle_callback(
                code="auth_code_123", state=helper._csrf_state, error=None
            )

        asyncio.create_task(simulate_callback())

        async for event in helper.run(
            callback_url="http://localhost:3000/callback",
            timeout=2.0,
            channel_name="test",
        ):
            events.append(event)

        assert len(events) >= 3
        assert events[0].state.status == LoginStatus.GENERATING
        assert events[1].state.status == LoginStatus.WAITING_USER_ACTION
        assert events[1].state.oauth_authorization_url is not None
        assert events[-2].state.status == LoginStatus.VALIDATING
        assert events[-1].state.status == LoginStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_oauth2_login_denied(self):
        """Test OAuth2 login user denial (error takes priority)."""
        helper = OAuth2LoginHelper(
            authorization_endpoint="https://auth.example.com/oauth/authorize",
            token_endpoint="https://auth.example.com/oauth/token",
            client_id="client123",
            client_secret="secret456",
            scope=["read"],
            callback_handler=self.mock_token_exchange,
        )

        events: list[LoginEvent] = []

        async def simulate_denial():
            while helper._csrf_state is None:
                await asyncio.sleep(0.05)
            await helper.handle_callback(
                code=None, state=helper._csrf_state, error="access_denied"
            )

        asyncio.create_task(simulate_denial())

        with pytest.raises(ChannelAuthError):
            async for event in helper.run(
                callback_url="http://localhost:3000/callback",
                timeout=2.0,
                channel_name="test",
            ):
                events.append(event)

        assert any(e.state.status == LoginStatus.FAILED for e in events)

    @pytest.mark.asyncio
    async def test_oauth2_csrf_state_mismatch_rejected(self):
        """Test that mismatched CSRF state is rejected as a security violation."""
        helper = OAuth2LoginHelper(
            authorization_endpoint="https://auth.example.com/oauth/authorize",
            token_endpoint="https://auth.example.com/oauth/token",
            client_id="client123",
            client_secret="secret456",
            scope=["read"],
            callback_handler=self.mock_token_exchange,
        )

        events: list[LoginEvent] = []

        async def simulate_bad_state():
            while helper._csrf_state is None:
                await asyncio.sleep(0.05)
            await helper.handle_callback(
                code="auth_code_123", state="wrong_state_value", error=None
            )

        asyncio.create_task(simulate_bad_state())

        with pytest.raises(ChannelAuthError, match="CSRF state mismatch"):
            async for event in helper.run(
                callback_url="http://localhost:3000/callback",
                timeout=2.0,
                channel_name="test",
            ):
                events.append(event)

        assert any(e.state.status == LoginStatus.FAILED for e in events)

    @pytest.mark.asyncio
    async def test_oauth2_login_cancel(self):
        """Test OAuth2 login cancellation."""
        helper = OAuth2LoginHelper(
            authorization_endpoint="https://auth.example.com/oauth/authorize",
            token_endpoint="https://auth.example.com/oauth/token",
            client_id="client123",
            client_secret="secret456",
            scope=["read"],
            callback_handler=self.mock_token_exchange,
        )

        events = []

        async def cancel_after_delay():
            await asyncio.sleep(0.2)
            helper.cancel()

        asyncio.create_task(cancel_after_delay())

        async for event in helper.run(
            callback_url="http://localhost:3000/callback",
            timeout=5.0,
            channel_name="test",
        ):
            events.append(event)

        assert any(e.state.status == LoginStatus.CANCELLED for e in events)
