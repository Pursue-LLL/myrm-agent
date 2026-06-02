# Channels Providers 模块架构

## 架构概览
定义具体渠道的实现类，通过适配外部平台 API 满足 BaseChannel 的统一发送、流式更新与长连保活要求。本层完全内聚底层细节，屏蔽复杂性。

## 目录结构

| 目录/文件 | 类型 | 职责 |
|-----------|------|------|
| `telegram/` | Provider | Telegram Bot API |
| `slack/` | Provider | Slack Events/Web API |
| `discord/` | Provider | Discord Bot (discord.py) |
| `feishu/` | Provider | 飞书/Feishu (lark-oapi) |
| `dingtalk/` | Provider | 钉钉/DingTalk |
| `msteams/` | Provider | Microsoft Teams |
| `whatsapp/` | Provider | WhatsApp (Baileys/Cloud API) |
| `qq/` | Provider | QQ |
| `onebot/` | Provider | QQ (OneBot/NapCat) |
| `line/` | Provider | LINE |
| `matrix/` | Provider | Matrix (mautrix + 可选 E2EE) |
| `mattermost/` | Provider | Mattermost |
| `signal/` | Provider | Signal |
| `wecom/` | Provider | 企业微信 (自建应用 + AI Bot) |
| `wechat/` | Provider | 微信 (iLink + Official Account) |
| `googlechat/` | Provider | Google Chat |
| `email.py` | Provider | Email (IMAP/SMTP) |
| `sms.py` | Provider | Twilio SMS |
| `irc.py` | Provider | IRC |
| `imessage.py` | Provider | iMessage |
| `zalo.py` | Provider | Zalo |
| `voice_channel.py` | Provider | Twilio 语音通话 (ConversationRelay) |
| `webhook.py` | Provider | 通用 Webhook |
| `_ilink/` | 内部共享库 | iLink Bot 协议客户端/加密/媒体/类型 |
| `_http_timeout.py` | 内部工具 | Channel API 超时配置 |
| `_twilio_utils.py` | 内部工具 | Twilio 签名验证 |
| `registry.py` | 核心 | 渠道注册表 (lazy-loading, thread-safe) |

## 企业微信双模式
- **wecom/channel.py**（自建应用）: AES-CBC 加密 XML 回调，需公网回调服务器，支持 OAuth、多媒体、@mention
- **wecom/aibot_channel.py**（AI Bot 长连接）: WebSocket 长连接，免公网 IP，原生流式回复，推荐首选

## 模块依赖
[INPUT]
- `channels.core.base::BaseChannel` (POS: 统一渠道契约)
- `channels.reliability.reconnect::reconnect_loop` (POS: 长连接重连)

[OUTPUT]
- 适配各种通信平台的渠道实例
- 渠道专有的底层机制（如企微的全量刷新心跳与极限界限抢救机制 Global Stream Guardian）

[POS]
具体通讯平台的底层接入层。负责协议适配、鉴权、重连以及平台专有的消息交付策略。