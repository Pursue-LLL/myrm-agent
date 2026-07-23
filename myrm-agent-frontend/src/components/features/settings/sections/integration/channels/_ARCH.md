# settings/sections/integration/channels 模块架构

## 架构概述

设置页「通信」域全部 UI：渠道连接卡片、DM/群组策略、渠道路由、语音 STT/TTS、配对与连接状态。由 `integration/CommunicationSection` 以 Tab 聚合本目录组件。

**渠道路由 Agent 策略**：UI 下拉仅 General Agent（`@/services/channels/channelAgentBinding`）；服务端 `SqlTopicManager.bind_topic` 写拒 + `resolve_topic`/`get_all_topics` 读清 legacy Search 绑定。

## 文件清单

| 文件 | 职责 |
|------|------|
| `ChannelsSection.tsx` | 渠道总览、安装依赖、各 Provider 配置卡片 |
| `ChannelRoutingSection.tsx` | 渠道路由页壳与布局 |
| `useChannelRouting.ts` | 渠道路由状态与 API 绑定 handlers；暴露 `channelBindableAgents`（`filterChannelBindableAgents(agents)` 结果，General-only） |
| `ChannelRoutingTopicRow.tsx` | 单 Topic 绑定行（Agent / 线程共享 / 回复模式） |
| `VoiceSection.tsx` | 语音输入输出设置 |
| `ChannelList.tsx` / `ChannelIcon.tsx` | 渠道列表与图标 |
| `ConnectionBadge.tsx` / `ChannelIngressBadge.tsx` / `PairingManager.tsx` | 连接状态、Ingress 提示与配对管理 |
| `useChannelsState.ts` / `useChannelConfig.ts` / `useConnectionStatusLabel.ts` | 渠道状态 hooks |
| `@/hooks/useIngressRequirement.ts` | Server `/system/ingress-requirement`；`ChannelsSection` 统一 `ChannelIngressBadge` |
| `*ConfigCard.tsx` / `WhatsAppCard.tsx` | 各平台配置 UI（全部在本目录） |
| `DmPolicySelector.tsx` / `GroupManager.tsx` | DM 策略与群组管理 |
| `NotificationChannelEditor.tsx` | 通知渠道编辑（Preferences 复用） |

## Reaction 配置链路

Settings `saveChannelsConfig` → DB `channels` → `config/router` 调用 `refresh_reaction_policy()` → `AgentRouter.set_reaction_policy()` → 入站 ack/completion/failure reaction（`router.py`）。

## 依赖

- `@/services/channels`
- `sections/SettingsSection.tsx`（相对 `../../SettingsSection`）
- `settings/common/SettingsSkeleton`（相对 `../../../common/SettingsSkeleton`）
- 父模块 [sections/_ARCH.md](../../_ARCH.md)
