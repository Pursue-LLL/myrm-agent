"""Channel connection test endpoints.

[INPUT]
- api.channels.schemas::各频道TestRequest/TestResponse (POS: Channel API 请求响应模型)
- api.dependencies::get_deploy_identity (POS: 用户身份认证依赖)

[OUTPUT]
- router: 16+ 频道连接测试端点

[POS]
频道连接测试路由。提供各频道凭据连通性验证端点，用于前端配置时实时测试。
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter

from app.api.channels.schemas import (
    ChannelTestResponse,
    DingTalkTestRequest,
    DingTalkTestResponse,
    DiscordTestRequest,
    EmailTestRequest,
    ExternalAgentTestRequest,
    FeishuTestRequest,
    FeishuTestResponse,
    GoogleChatTestRequest,
    IMessageTestRequest,
    IRCTestRequest,
    LINETestRequest,
    MatrixTestRequest,
    MattermostTestRequest,
    QQTestRequest,
    SignalTestRequest,
    SlackTestRequest,
    SMSTestRequest,
    TeamsTestRequest,
    TelegramTestRequest,
    TestInboundRequest,
    VoiceTestRequest,
    WeComTestRequest,
    ZaloTestRequest,
)

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post("/feishu/test", response_model=FeishuTestResponse)
async def feishu_test_connection(
    body: FeishuTestRequest,
) -> FeishuTestResponse:
    """Test Feishu API connectivity with the provided credentials."""
    from app.channels.providers.feishu.api import FeishuClient

    client = FeishuClient(body.app_id, body.app_secret, use_lark=body.use_lark)
    try:
        ok = await client.verify_connectivity()
        return FeishuTestResponse(
            ok=ok,
            message="Connection successful" if ok else "Token verification failed",
        )
    except Exception as e:
        return FeishuTestResponse(ok=False, message=str(e))
    finally:
        await client.close()


@router.post("/dingtalk/test", response_model=DingTalkTestResponse)
async def dingtalk_test_connection(
    body: DingTalkTestRequest,
) -> DingTalkTestResponse:
    """Test DingTalk API connectivity with the provided credentials."""
    from app.core.channel_bridge.providers.dingtalk_api import DingTalkClient

    client = DingTalkClient(body.client_id, body.client_secret)
    try:
        ok = await client.verify_token()
        return DingTalkTestResponse(
            ok=ok,
            message="Connection successful" if ok else "Token verification failed",
        )
    except Exception as e:
        return DingTalkTestResponse(ok=False, message=str(e))
    finally:
        await client.close()


@router.post("/slack/test", response_model=ChannelTestResponse)
async def slack_test_connection(
    body: SlackTestRequest,
) -> ChannelTestResponse:
    """Test Slack API connectivity with the provided credentials."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as http:
        try:
            resp = await http.post(
                "https://slack.com/api/auth.test",
                headers={"Authorization": f"Bearer {body.bot_token}"},
            )
            data = resp.json()
            ok = bool(data.get("ok"))
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else f"Auth failed: {data.get('error', 'unknown')}",
            )
        except Exception as e:
            return ChannelTestResponse(ok=False, message=str(e))


@router.post("/discord/test", response_model=ChannelTestResponse)
async def discord_test_connection(
    body: DiscordTestRequest,
) -> ChannelTestResponse:
    """Test Discord API connectivity with the provided bot token."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as http:
        resp = await http.get(
            "https://discord.com/api/v10/users/@me",
            headers={"Authorization": f"Bot {body.bot_token}"},
        )
        ok = resp.status_code == 200
        return ChannelTestResponse(
            ok=ok,
            message="Connection successful" if ok else f"HTTP {resp.status_code}",
        )


@router.post("/wecom/test", response_model=ChannelTestResponse)
async def wecom_test_connection(
    body: WeComTestRequest,
) -> ChannelTestResponse:
    """Test WeCom API connectivity with the provided credentials."""
    import httpx

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                "https://qyapi.weixin.qq.com/cgi-bin/gettoken",
                params={"corpid": body.corp_id, "corpsecret": body.corp_secret},
                timeout=10.0,
            )
            data = resp.json()
            ok = resp.status_code == 200 and data.get("errcode", -1) == 0
            msg = "Connection successful" if ok else f"Error: {data.get('errmsg', 'Unknown')}"
            return ChannelTestResponse(ok=ok, message=msg)
        except Exception as e:
            return ChannelTestResponse(ok=False, message=str(e))


@router.post("/teams/test", response_model=ChannelTestResponse)
async def teams_test_connection(
    body: TeamsTestRequest,
) -> ChannelTestResponse:
    """Test MS Teams API connectivity with the provided credentials."""
    import httpx

    tenant = body.tenant_id or "botframework.com"
    url = f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token"
    try:
        async with httpx.AsyncClient(timeout=15.0) as http:
            resp = await http.post(
                url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": body.app_id,
                    "client_secret": body.app_password,
                    "scope": "https://api.botframework.com/.default",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            ok = bool(data.get("access_token"))
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else "OAuth token verification failed",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=str(e))


@router.post("/matrix/test", response_model=ChannelTestResponse)
async def matrix_test_connection(
    body: MatrixTestRequest,
) -> ChannelTestResponse:
    """Test Matrix API connectivity with the provided credentials."""
    import httpx

    async with httpx.AsyncClient(timeout=10) as http:
        url = f"{body.homeserver_url.rstrip('/')}/_matrix/client/v3/account/whoami"
        resp = await http.get(
            url,
            headers={"Authorization": f"Bearer {body.access_token}"},
        )
        ok = resp.status_code == 200
        msg = "Connection successful" if ok else f"HTTP {resp.status_code}"
        if ok:
            data = resp.json()
            msg = f"Connected as {data.get('user_id', 'unknown')}"
        return ChannelTestResponse(ok=ok, message=msg)


@router.post("/telegram/test", response_model=ChannelTestResponse)
async def telegram_test_connection(
    body: TelegramTestRequest,
) -> ChannelTestResponse:
    """Test Telegram Bot API connectivity with the provided token."""
    from app.channels.providers.telegram.api import TelegramClient

    client = TelegramClient(body.bot_token)
    try:
        me = await client.get_me()
        username = me.get("username", "unknown")
        return ChannelTestResponse(ok=True, message=f"Connected as @{username}")
    except Exception as e:
        return ChannelTestResponse(ok=False, message=str(e))
    finally:
        await client.close()


@router.post("/googlechat/test", response_model=ChannelTestResponse)
async def googlechat_test_connection(
    body: GoogleChatTestRequest,
) -> ChannelTestResponse:
    """Test Google Chat API connectivity with the provided service account."""
    from app.channels.providers.googlechat.api import GoogleChatClient

    client = GoogleChatClient(body.service_account_json)
    try:
        ok = await client.verify_token()
        return ChannelTestResponse(
            ok=ok,
            message="Connection successful" if ok else "Token verification failed",
        )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=str(e))
    finally:
        await client.close()


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


@router.post("/qq/test", response_model=ChannelTestResponse)
async def qq_test_connection(
    body: QQTestRequest,
) -> ChannelTestResponse:
    """Test QQ Bot API connectivity."""
    import httpx

    try:
        async with httpx.AsyncClient(timeout=10) as http:
            resp = await http.post(
                "https://bots.qq.com/app/getAppAccessToken",
                json={"appId": body.app_id, "clientSecret": body.client_secret},
            )
            ok = resp.status_code == 200 and "access_token" in resp.json()
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else f"HTTP {resp.status_code}",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=str(e))


@router.post("/email/test", response_model=ChannelTestResponse)
async def email_test_connection(
    body: EmailTestRequest,
) -> ChannelTestResponse:
    """Test IMAP connectivity."""
    import asyncio
    import imaplib

    def _check() -> tuple[bool, str]:
        try:
            conn = imaplib.IMAP4_SSL(body.imap_host, body.imap_port)
            conn.login(body.username, body.password)
            conn.noop()
            conn.logout()
            return True, "IMAP connection successful"
        except Exception as e:
            return False, str(e)

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
        return ChannelTestResponse(ok=False, message=str(e))


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
        return ChannelTestResponse(ok=False, message=str(e))


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
        return ChannelTestResponse(ok=False, message=str(e))


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
        return ChannelTestResponse(ok=False, message=str(e))


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
            return ChannelTestResponse(
                ok=ok,
                message="Connection successful" if ok else f"HTTP {resp.status_code}",
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=str(e))


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
        return ChannelTestResponse(ok=False, message=str(e))


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
        return ChannelTestResponse(ok=False, message=str(e))


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
        return ChannelTestResponse(ok=False, message=str(e))


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

    version: str | None = None
    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                found,
                "--version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
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
