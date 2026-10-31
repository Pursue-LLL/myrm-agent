"""Channel connection test endpoints.

[INPUT]
- api.channels.connection_probes::router, safe_err_msg (POS: probes for the hosted messaging platforms, error text)
- api.channels.schemas::*TestRequest, *TestResponse (POS: request and response models of the channel API)

[OUTPUT]
- router: ``POST /{channel}/test`` for every channel, ``POST /test-inbound`` and ``POST /external-agents/test``

[POS]
Channel connection test routes. Each probe checks the credentials of the settings form against the live service, so
the page can tell the user at once whether they work. The messaging-platform probes live in ``connection_probes``;
this module mounts them and keeps the mail, telephony, bridge and IRC probes, the external-agent probe and the
simulated inbound message.
"""

from __future__ import annotations

import asyncio
import imaplib
import ssl

from fastapi import APIRouter

from app.api.channels.connection_probes import router as bot_platforms_router
from app.api.channels.connection_probes import safe_err_msg
from app.api.channels.schemas import (
    ChannelTestResponse,
    EmailTestRequest,
    ExternalAgentTestRequest,
    IMessageTestRequest,
    IRCTestRequest,
    LINETestRequest,
    MattermostTestRequest,
    SignalTestRequest,
    SMSTestRequest,
    TestInboundRequest,
    VoiceTestRequest,
    ZaloTestRequest,
)

router = APIRouter()
router.include_router(bot_platforms_router)

# Seconds the settings page waits on a mail server that does not answer, in line with the other connectivity probes.
_IMAP_TEST_TIMEOUT = 10


@router.post("/test-inbound", status_code=202)
async def test_inbound(
    body: TestInboundRequest,
) -> dict[str, str]:
    """Inject a simulated inbound message for testing."""
    from app.channels.types import InboundMessage
    from app.core.channel_bridge import channel_gateway

    msg = InboundMessage(
        channel=body.channel,
        sender_id=body.sender_id,
        content=body.content,
        chat_id=body.sender_id,
    )
    await channel_gateway.bus._handle_inbound(msg)
    return {"status": "queued"}


@router.post("/email/test", response_model=ChannelTestResponse)
async def email_test_connection(
    body: EmailTestRequest,
) -> ChannelTestResponse:
    """Test IMAP connectivity."""

    def _check() -> tuple[bool, str]:
        try:
            conn = imaplib.IMAP4_SSL(
                body.imap_host,
                body.imap_port,
                ssl_context=ssl.create_default_context(),
                timeout=_IMAP_TEST_TIMEOUT,
            )
            conn.login(body.username, body.password)
            conn.noop()
            conn.logout()
            return True, "IMAP connection successful"
        except Exception as e:
            return False, safe_err_msg(e)

    ok, msg = await asyncio.to_thread(_check)
    return ChannelTestResponse(ok=ok, message=msg)


@router.post("/voice/test", response_model=ChannelTestResponse)
async def voice_test_connection(
    body: VoiceTestRequest,
) -> ChannelTestResponse:
    """Test Twilio API connectivity."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{body.account_sid}.json",
                auth=(body.account_sid, body.auth_token),
            )
            ok = resp.status_code == 200
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else f"HTTP {resp.status_code}",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/sms/test", response_model=ChannelTestResponse)
async def sms_test_connection(
    body: SMSTestRequest,
) -> ChannelTestResponse:
    """Test Twilio SMS connectivity by verifying account and phone number ownership."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{body.account_sid}.json",
                auth=(body.account_sid, body.auth_token),
            )
            if resp.status_code != 200:
                return ChannelTestResponse(ok=False, message=f"HTTP {resp.status_code}")
            numbers_resp = await http.get(
                f"https://api.twilio.com/2010-04-01/Accounts/{body.account_sid}"
                f"/IncomingPhoneNumbers.json?PhoneNumber={body.phone_number}",
                auth=(body.account_sid, body.auth_token),
            )
            if numbers_resp.status_code == 200:
                data = numbers_resp.json()
                phones = data.get("incoming_phone_numbers", [])
                if phones:
                    return ChannelTestResponse(ok=True, message="Connection successful")
                return ChannelTestResponse(
                    ok=False,
                    message=f"Phone number {body.phone_number} not found in account",
                )
            return ChannelTestResponse(ok=True, message="Connection successful (phone check skipped)")
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/signal/test", response_model=ChannelTestResponse)
async def signal_test_connection(
    body: SignalTestRequest,
) -> ChannelTestResponse:
    """Test Signal CLI REST API connectivity."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(f"{body.api_url.rstrip('/')}/v1/about")
            ok = resp.status_code == 200
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else f"HTTP {resp.status_code}",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/line/test", response_model=ChannelTestResponse)
async def line_test_connection(
    body: LINETestRequest,
) -> ChannelTestResponse:
    """Test LINE Messaging API connectivity."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                "https://api.line.me/v2/bot/info",
                headers={"Authorization": f"Bearer {body.channel_access_token}"},
            )
            ok = resp.status_code == 200
            if ok:
                data = resp.json()
                msg = f"Connected as {data.get('displayName', 'unknown')}"
            else:
                msg = f"HTTP {resp.status_code}"
            return ChannelTestResponse(ok=ok, message=msg)
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/imessage/test", response_model=ChannelTestResponse)
async def imessage_test_connection(
    body: IMessageTestRequest,
) -> ChannelTestResponse:
    """Test BlueBubbles API connectivity."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"{body.api_url.rstrip('/')}/api/v1/server/info",
                params={"password": body.password},
            )
            ok = resp.status_code == 200
            if ok:
                try:
                    payload = resp.json()
                    data = payload.get("data", {}) if isinstance(payload, dict) else {}
                    if isinstance(data, dict):
                        p_api = bool(data.get("private_api"))
                        h_conn = bool(data.get("helper_connected"))
                        message = (
                            f"Connection successful (Private API: {'enabled' if p_api else 'disabled'}, "
                            f"Helper: {'connected' if h_conn else 'disconnected'})"
                        )
                    else:
                        message = "Connection successful"
                except Exception:
                    message = "Connection successful"
            else:
                message = f"HTTP {resp.status_code}"
            return ChannelTestResponse(
                ok=ok,
                message=message,
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/irc/test", response_model=ChannelTestResponse)
async def irc_test_connection(
    body: IRCTestRequest,
) -> ChannelTestResponse:
    """Test IRC server TCP connectivity."""
    try:
        _, writer = await asyncio.wait_for(
            asyncio.open_connection(body.server, body.port),
            timeout=10,
        )
        writer.close()
        await writer.wait_closed()
        return ChannelTestResponse(
            ok=True,
            message=f"TCP connection to {body.server}:{body.port} successful",
        )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/zalo/test", response_model=ChannelTestResponse)
async def zalo_test_connection(
    body: ZaloTestRequest,
) -> ChannelTestResponse:
    """Test Zalo OA API connectivity."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                "https://openapi.zalo.me/v3.0/oa/getoa",
                headers={"access_token": body.access_token},
            )
            ok = resp.status_code == 200
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else f"HTTP {resp.status_code}",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/mattermost/test", response_model=ChannelTestResponse)
async def mattermost_test_connection(
    body: MattermostTestRequest,
) -> ChannelTestResponse:
    """Test Mattermost server connectivity with Bot Access Token."""
    import httpx

    try:
        api_url = f"{body.server_url.rstrip('/')}/api/v4"
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.get(
                f"{api_url}/users/me",
                headers={"Authorization": f"Bearer {body.access_token}"},
            )
            if resp.status_code == 200:
                data: dict[str, object] = resp.json()
                username = data.get("username", "")
                return ChannelTestResponse(
                    ok=True,
                    message=f"Connected as @{username}",
                )
            return ChannelTestResponse(
                ok=False,
                message=f"HTTP {resp.status_code}",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


@router.post("/external-agents/test", response_model=ChannelTestResponse)
async def test_external_agent(
    body: ExternalAgentTestRequest,
) -> ChannelTestResponse:
    """Test if an external agent command is available on the system."""
    import shutil

    command = body.command.strip()
    if not command:
        return ChannelTestResponse(ok=False, message="Command is empty")

    found = shutil.which(command)
    if not found:
        return ChannelTestResponse(ok=False, message=f"Command '{command}' not found in PATH")

    from myrm_agent_harness.api import (
        EnvInheritPolicy,
        build_isolated_child_env,
    )

    version: str | None = None
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                found,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=build_isolated_child_env(inherit_policy=EnvInheritPolicy.CORE),
            ),
            timeout=10,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=10)
        output = stdout.decode("utf-8", errors="replace").strip()
        if output:
            version = output.split("\n")[0].strip()
    except (TimeoutError, OSError):
        pass

    msg = f"Found at {found}"
    if version:
        msg += f" ({version})"
    return ChannelTestResponse(ok=True, message=msg)
