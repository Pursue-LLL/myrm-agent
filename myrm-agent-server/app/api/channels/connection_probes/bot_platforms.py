"""Credential probes for the hosted messaging platforms.

[INPUT]
- api.channels.schemas::*TestRequest, *TestResponse (POS: request and response models of the channel API)
- api.channels.connection_probes.error_text::safe_err_msg (POS: credential-safe error text)

[OUTPUT]
- router: ``POST /{platform}/test`` for Feishu, DingTalk, Slack, Discord, WeCom, Teams, Matrix, Telegram, Google Chat, QQ

[POS]
Each probe calls the platform with the credentials of the form and answers whether they work. The platform clients
are imported inside the handlers: a probe is the only reason to load them while the page is open.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.channels.connection_probes.error_text import safe_err_msg
from app.api.channels.schemas import (
    ChannelTestResponse,
    DingTalkTestRequest,
    DingTalkTestResponse,
    DiscordTestRequest,
    FeishuTestRequest,
    FeishuTestResponse,
    GoogleChatTestRequest,
    MatrixTestRequest,
    QQTestRequest,
    SlackTestRequest,
    TeamsTestRequest,
    TelegramTestRequest,
    TelegramTestResponse,
    WeComTestRequest,
)

router = APIRouter()


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
        return FeishuTestResponse(ok=False, message=safe_err_msg(e))
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
        return DingTalkTestResponse(ok=False, message=safe_err_msg(e))
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
                message=("Connection successful" if ok else f"Auth failed: {data.get('error', 'unknown')}"),
            )
        except Exception as e:
            return ChannelTestResponse(ok=False, message=safe_err_msg(e))


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
            return ChannelTestResponse(ok=False, message=safe_err_msg(e))


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
                message=("Connection successful" if ok else "OAuth token verification failed"),
            )
    except Exception as e:
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))


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


@router.post("/telegram/test", response_model=TelegramTestResponse, response_model_exclude_none=True)
async def telegram_test_connection(
    body: TelegramTestRequest,
) -> TelegramTestResponse:
    """Test Telegram Bot API connectivity with the provided token."""
    from app.channels.providers.telegram.api import TelegramClient
    from app.channels.providers.telegram.api_core import getme_failure_reason

    client = TelegramClient(body.bot_token, proxy=body.proxy or None)
    try:
        me = await client.get_me()
        username = me.get("username", "unknown")
        return TelegramTestResponse(ok=True, message=f"Connected as @{username}")
    except Exception as e:
        return TelegramTestResponse(ok=False, message=safe_err_msg(e), reason=getme_failure_reason(e).value)
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
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))
    finally:
        await client.close()


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
        return ChannelTestResponse(ok=False, message=safe_err_msg(e))
