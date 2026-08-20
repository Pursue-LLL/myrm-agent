# settings/sections/integration/channels 模块架构

## 架构概述

设置页「通信」域全部 UI：渠道连接卡片、DM/群组策略、渠道路由、语音 STT/TTS、配对与连接状态。由 `integration/CommunicationSection` 以 Tab 聚合本目录组件。

**渠道路由 Agent 策略**：UI 下拉仅 General Agent（`@/services/channels/channelAgentBinding`）；服务端 `SqlTopicManager.bind_topic` 写拒 + `resolve_topic`/`get_all_topics` 读清 legacy Search 绑定。

## 文件清单

| 文件                                                                          | 职责                                                                                                                       |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `ChannelsSection.tsx`                                                         | 渠道总览、安装依赖、各 Provider 配置卡片                                                                                   |
| `ChannelRoutingSection.tsx`                                                   | 渠道路由页壳与布局                                                                                                         |
| `useChannelRouting.ts`                                                        | 渠道路由状态与 API 绑定 handlers；暴露 `channelBindableAgents`（`filterChannelBindableAgents(agents)` 结果，General-only） |
| `ChannelRoutingTopicRow.tsx`                                                  | 单 Topic 绑定行（Agent / Project workspace / 线程共享 / 回复模式）；展示 `{项目名} · {路径}`                               |
| `topicWorkspaceLabel.ts`                                                      | `resolveTopicWorkspaceDisplayLabel`：从已加载 projects 解析人类可读 workspace 路径                                         |
| `VoiceSection.tsx`                                                            | 语音输入输出设置                                                                                                           |
| `ChannelList.tsx` / `ChannelIcon.tsx`                                         | 渠道列表与图标                                                                                                             |
| `ConnectionBadge.tsx` / `ChannelIngressBadge.tsx` / `PairingManager.tsx`      | 连接状态、Ingress 提示与配对管理                                                                                           |
| `useChannelsState.ts` / `useChannelConfig.ts` / `useConnectionStatusLabel.ts` | 渠道状态 hooks                                                                                                             |
| `@/hooks/billing/useIngressRequirement.ts`                                    | Server `/system/ingress-requirement`；`ChannelsSection` 统一 `ChannelIngressBadge`                                         |
| `*ConfigCard.tsx` / `WhatsAppCard.tsx`                                        | 各平台配置 UI（含 `WeChatOfficialConfigCard` 认证服务号凭证 + 动态出口 IP 复制/刷新 + IP 白名单指引）                      |
| `FeishuQrRegisterDialog.tsx`                                                  | 飞书 QR 扫码注册弹窗（新增多应用实例 / 刷新默认实例；含失败快速响应 + `resolvedRef` 终态守卫）                             |
| `FeishuCredentialsEditDialog.tsx`                                             | 多应用实例「编辑凭据」弹窗（App ID / Secret / Lark；Secret 留空保留旧值，merge 落库后重建实例生效）                        |
| `FeishuMultiAppSection.tsx`                                                   | 飞书多应用管理区（实例列表/添加/删除/重命名/编辑凭据，上限 UX；删除实例不可逆，需二次确认）                                |
| `DmPolicySelector.tsx` / `GroupManager.tsx`                                   | DM 策略与群组管理                                                                                                          |
| `NotificationChannelEditor.tsx`                                               | 通知渠道编辑（Preferences 复用）                                                                                           |

## 测试

- `__tests__/topicWorkspaceLabel.test.ts` — workspace 展示 label 解析
- `__tests__/FeishuMultiAppSection.test.tsx` — 多应用区渲染/编辑/删除确认/重命名/上限 UX（删除确认：确认后真实调 `deleteChannelInstance`、取消保留实例）
- `__tests__/WeChatConfigCard.test.tsx` — 微信卡片删除/登出确认（主账号登出二次确认后调 `logoutWeChatChannel`、取消保留；附加实例删除确认后调 `deleteChannelInstance`）
- 后端 `tests/e2e/test_channel_delete_confirmation_chrome_e2e.py` — 删除确认 Chrome MCP E2E（PRIVATE：主账号登出取消/确认 + wechat extra 实例删除取消/确认 + 删除失败容错保持对话框打开，均走真实 API；依赖本模块 `ConfirmDialog` 的 `data-testid="confirm-dialog-confirm/cancel"` 探针）
- `__tests__/FeishuCredentialsEditDialog.test.tsx` — 编辑凭据弹窗（脱敏回显、留空保留、校验）
- `__tests__/FeishuQrRegisterDialog.test.tsx` — QR 注册弹窗（扫描/超时/手动回退）

## Reaction 配置链路

Settings `saveChannelsConfig` → DB `channels` → `config/router` 调用 `refresh_reaction_policy()` → `AgentRouter.set_reaction_policy()` → 入站 ack/completion/failure reaction（`router.py`）。

## 依赖

- `@/services/channels`
- `sections/SettingsSection.tsx`（相对 `../../SettingsSection`）
- `settings/common/SettingsSkeleton`（相对 `../../../common/SettingsSkeleton`）
- 父模块 [sections/_ARCH.md](../../_ARCH.md)
