# settings/sections/personal/ 模块架构

## 架构概述

Settings「Personal」分组：账户、偏好与个性化 Tab Section。

## 文件清单

| 文件                         | 职责                                                                                                                                                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `AccountSection.tsx`         | 账户信息与凭据                                                                                                                                                                                         |
| `PreferencesSection.tsx`     | 通用偏好（语言、主题等）；含 `LinkEmbedSettings`、`WebPushCard`（`usePushSubscription` SSOT）与 `VoiceSessionToggles`                                                                                  |
| `LinkEmbedSettings.tsx`      | 链接嵌入偏好卡片：嵌入模式下拉（由卡片标题命名、由说明文字描述）与已允许的提供方清单；回归 `__tests__/LinkEmbedSettings.test.tsx`                                                                      |
| `VoiceSessionToggles.tsx`    | 语音会话开关卡片（会话、全双工、Agent 桥接）：经 `voiceDeviceSettings` 读写，浏览器拒绝存储时开关在本页内仍然生效，同页其他写入与其他标签的改动实时反映；回归 `__tests__/VoiceSessionToggles.test.tsx` |
| `WebPushCard.tsx`            | Personal 分组 Web Push 开关 + iOS PWA 引导 + 测试推送                                                                                                                                                  |
| `PersonalizationSection.tsx` | 个性化与伴侣相关选项                                                                                                                                                                                   |

## 依赖

- [sections/_ARCH.md](../_ARCH.md)
- `@/store/useConfigStore` — 设置草稿与同步
- `@/store/useEmbedConsentStore` — Link Embeds 模式（ask/always/off）与 per-provider allowlist
- `@/hooks/voice/voiceDeviceSettings` — 语音设置的设备端读写层（与聊天语音按钮共用）
