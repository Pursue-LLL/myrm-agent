"""Pydantic schemas for the channels API.

[INPUT]
(无外部依赖)

[OUTPUT]
- ChannelStatusResponse, PairingCreate, PairingResponse: 请求/响应模型
- ChannelInstallDependenciesResponse: lazy-install 结果（ok/message/registered）

[POS]
Channel 管理 API 数据模型。定义 Channel 状态查询和账号绑定的 schema。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class ChannelIssueResponse(BaseModel):
    kind: str
    severity: str
    message: str
    fix: str = ""


class ChannelStatusResponse(BaseModel):
    name: str
    status: str
    connected: bool = False
    channel_type: str = Field("", alias="channelType")
    instance_id: str = Field("", alias="instanceId")
    display_name: str = Field("", alias="displayName")
    last_inbound_at: float | None = None
    last_outbound_at: float | None = None
    last_active_at: float | None = None
    issues: list[ChannelIssueResponse] = []

    class Config:
        populate_by_name = True


class ChannelToggleRequest(BaseModel):
    enabled: bool


class ChannelToggleResponse(BaseModel):
    name: str
    enabled: bool
    status: str
    connected: bool = False


class ChannelInstallDependenciesResponse(BaseModel):
    ok: bool
    message: str
    registered: bool = True


class PairingCreate(BaseModel):
    channel: str = Field(..., min_length=1, max_length=50)
    sender_id: str = Field(..., min_length=1, max_length=255)


class PairingResponse(BaseModel):
    id: str
    channel: str
    sender_id: str
    user_id: str
    status: str
    display_name: str | None = None
    created_at: datetime
    updated_at: datetime


class PairingStatusUpdate(BaseModel):
    status: Literal["active", "blocked"] | None = None
    display_name: str | None = None


class WhatsAppStatusResponse(BaseModel):
    connected: bool
    status: str = "idle"
    qr_code: str | None = None
    phone_number: str | None = None


class WeChatStatusResponse(BaseModel):
    connected: bool
    qr_code: str | None = None
    bot_id: str | None = None
    status: str = "disconnected"
    error: str | None = None


class TestInboundRequest(BaseModel):
    channel: str = Field(..., min_length=1)
    sender_id: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)


class GroupInfoResponse(BaseModel):
    jid: str
    name: str
    channel: str
    is_enabled: bool


class EnabledGroupsUpdate(BaseModel):
    enabled_groups: list[str]


class FeishuTestRequest(BaseModel):
    app_id: str = Field(..., alias="appId", min_length=1)
    app_secret: str = Field(..., alias="appSecret", min_length=1)
    use_lark: bool = Field(False, alias="useLark")

    class Config:
        populate_by_name = True


class FeishuTestResponse(BaseModel):
    ok: bool
    message: str


class DingTalkTestRequest(BaseModel):
    client_id: str = Field(..., alias="clientId", min_length=1)
    client_secret: str = Field(..., alias="clientSecret", min_length=1)

    class Config:
        populate_by_name = True


class DingTalkTestResponse(BaseModel):
    ok: bool
    message: str


class SlackTestRequest(BaseModel):
    bot_token: str = Field(..., alias="botToken", min_length=1)
    app_token: str = Field(..., alias="appToken", min_length=1)

    class Config:
        populate_by_name = True


class DiscordTestRequest(BaseModel):
    bot_token: str = Field(..., alias="botToken", min_length=1)

    class Config:
        populate_by_name = True


class WeComTestRequest(BaseModel):
    corp_id: str = Field(..., alias="corpId", min_length=1)
    corp_secret: str = Field(..., alias="corpSecret", min_length=1)

    class Config:
        populate_by_name = True


class TeamsTestRequest(BaseModel):
    app_id: str = Field(..., alias="appId", min_length=1)
    app_password: str = Field(..., alias="appPassword", min_length=1)
    tenant_id: str = Field("", alias="tenantId")

    class Config:
        populate_by_name = True


class MatrixTestRequest(BaseModel):
    homeserver_url: str = Field(..., alias="homeserverUrl", min_length=1)
    access_token: str = Field(..., alias="accessToken", min_length=1)

    class Config:
        populate_by_name = True


class TelegramTestRequest(BaseModel):
    bot_token: str = Field(..., alias="botToken", min_length=1)

    class Config:
        populate_by_name = True


class GoogleChatTestRequest(BaseModel):
    service_account_json: str = Field(..., alias="serviceAccountJson", min_length=1)

    class Config:
        populate_by_name = True


class QQTestRequest(BaseModel):
    app_id: str = Field(..., alias="appId", min_length=1)
    client_secret: str = Field(..., alias="clientSecret", min_length=1)

    class Config:
        populate_by_name = True


class EmailTestRequest(BaseModel):
    imap_host: str = Field(..., alias="imapHost", min_length=1)
    imap_port: int = Field(993, alias="imapPort")
    username: str = Field(..., min_length=1)
    password: str = Field(..., min_length=1)

    class Config:
        populate_by_name = True


class VoiceTestRequest(BaseModel):
    account_sid: str = Field(..., alias="accountSid", min_length=1)
    auth_token: str = Field(..., alias="authToken", min_length=1)

    class Config:
        populate_by_name = True


class SMSTestRequest(BaseModel):
    account_sid: str = Field(..., alias="accountSid", min_length=1)
    auth_token: str = Field(..., alias="authToken", min_length=1)
    phone_number: str = Field(..., alias="phoneNumber", min_length=1)

    class Config:
        populate_by_name = True


class SignalTestRequest(BaseModel):
    api_url: str = Field(..., alias="apiUrl", min_length=1)
    phone_number: str = Field(..., alias="phoneNumber", min_length=1)

    class Config:
        populate_by_name = True


class LINETestRequest(BaseModel):
    channel_access_token: str = Field(..., alias="channelAccessToken", min_length=1)

    class Config:
        populate_by_name = True


class IMessageTestRequest(BaseModel):
    api_url: str = Field(..., alias="apiUrl", min_length=1)
    password: str = Field(..., min_length=1)

    class Config:
        populate_by_name = True


class IRCTestRequest(BaseModel):
    server: str = Field(..., min_length=1)
    port: int = Field(6667)
    nick: str = Field(..., min_length=1)

    class Config:
        populate_by_name = True


class ZaloTestRequest(BaseModel):
    access_token: str = Field(..., alias="accessToken", min_length=1)

    class Config:
        populate_by_name = True


class MattermostTestRequest(BaseModel):
    server_url: str = Field(..., alias="serverUrl", min_length=1)
    access_token: str = Field(..., alias="accessToken", min_length=1)

    class Config:
        populate_by_name = True


class ExternalAgentTestRequest(BaseModel):
    command: str = Field(..., min_length=1)


class ChannelTestResponse(BaseModel):
    ok: bool
    message: str


class ChannelInstanceCreate(BaseModel):
    channel_type: str = Field(..., alias="channelType", min_length=1, max_length=50)
    display_name: str = Field("", alias="displayName", max_length=100)
    credentials: dict[str, str] | None = None

    class Config:
        populate_by_name = True


class ChannelInstanceResponse(BaseModel):
    instance_id: str = Field(..., alias="instanceId")
    channel_type: str = Field(..., alias="channelType")
    channel_name: str = Field(..., alias="channelName")
    display_name: str = Field("", alias="displayName")
    status: str

    class Config:
        populate_by_name = True


class TopicBindingResponse(BaseModel):
    topic_id: str = Field(..., alias="topicId")
    agent_id: str | None = Field(None, alias="agentId")
    enabled: bool = True
    bound_at: str | None = Field(None, alias="boundAt")
    display_name: str | None = Field(None, alias="displayName")
    avatar_url: str | None = Field(None, alias="avatarUrl")
    thread_sharing_mode: str = Field(default="isolated", alias="threadSharingMode")
    reply_mode: str = Field(default="auto", alias="replyMode")
    draft_timeout_minutes: int = Field(default=5, alias="draftTimeoutMinutes")
    draft_timeout_action: str = Field(default="auto_reject", alias="draftTimeoutAction")

    class Config:
        populate_by_name = True


class ChannelTopicsResponse(BaseModel):
    channel: str
    global_agent_id: str | None = Field(None, alias="globalAgentId")
    topics: list[TopicBindingResponse]

    class Config:
        populate_by_name = True


class DisplayNameUpdate(BaseModel):
    display_name: str = Field(..., alias="displayName", min_length=1, max_length=100)

    class Config:
        populate_by_name = True


class BindTopicRequest(BaseModel):
    agent_id: str | None = Field(None, alias="agentId")
    display_name: str | None = Field(None, alias="displayName")
    avatar_url: str | None = Field(None, alias="avatarUrl")
    thread_sharing_mode: str | None = Field(None, alias="threadSharingMode")
    reply_mode: Literal["auto", "draft_review"] | None = Field(None, alias="replyMode")
    draft_timeout_minutes: int | None = Field(None, alias="draftTimeoutMinutes")
    draft_timeout_action: Literal["auto_send", "auto_reject"] | None = Field(None, alias="draftTimeoutAction")

    class Config:
        populate_by_name = True
