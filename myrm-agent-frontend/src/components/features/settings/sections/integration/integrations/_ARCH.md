# settings/sections/integration/integrations/ 模块架构

## 架构概述

Settings「Integration」下的第三方集成目录：Catalog 浏览与连接、集成记忆。

## 文件清单

| 文件                                 | 职责                                                                                                                                                                                                                                                                  |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `IntegrationCatalogSection.tsx`      | 集成服务目录：卡片按已保存的 MCP 服务派生连接状态（可连接 / 已连接 / 已停用，后两者以状态标签 + 「管理」跳转 `/settings/mcp` 取代连接按钮），分类标签走 i18n（未收录分类回退原 id），官网外链触屏常显、悬停/键盘聚焦显现并带名称化 `aria-label`；同页挂载生命周期出站 Webhook 与 A2A 节点配置入口 |
| `IntegrationCatalogSection.test.tsx` | 目录区行为级单测：加载后渲染卡片、按中文标签与官方中文名过滤、无结果提示、点击卡片打开/确认关闭连接对话框、已连接/已停用卡片的状态与管理链接、保存服务后卡片即时转为已连接、官网外链可访问性、分类标签 i18n 与回退                                                                |
| `CatalogConnectionStatus.tsx`        | 目录服务连接状态标签（已连接 / 已停用），目录卡片与首装工具连接步骤共用，保证状态外观与文案一致                                                                                                                                                                       |
| `CatalogConnectionStatus.test.tsx`   | 状态标签单测：已连接为成功色、已停用为弱化色                                                                                                                                                                                                                          |
| `catalog-connection.ts`              | 目录条目连接状态 SSOT：以 `mcpConfig.name` 对照已保存 MCP 服务（与连接对话框的重复守卫同一身份）派生 `available` / `connected` / `disabled`，及订阅配置 store 的 hook                                                                                                  |
| `catalog-connection.test.ts`         | 连接状态单测：身份匹配、`enabled === false`、缺失/非字符串模板名，以及随 store 变化的 hook 响应                                                                                                                                                                       |
| `catalog-locale.ts`                  | 目录文案语言 SSOT：目录只提供中英文案，所有中文变体（zh / zh-TW …）读中文、其余语言读英文；提供纯函数与基于 next-intl 当前语言的 hook                                                                                                                                  |
| `catalog-locale.test.ts`             | 目录文案语言单测：中文变体归一与 hook 跟随 UI 语言                                                                                                                                                                                                                    |
| `LifecycleWebhookSection.tsx`        | 生命周期出站 Webhook 管理卡片：端点 CRUD（含卡片内 Edit 抽屉）、Agent Profile 范围选择、事件多选（至少 1 项 · 六国 i18n）、HMAC 徽标（`has_secret`）、`/{id}/ping` 探测；响应式 sm:flex 布局                                                                          |
| `A2APeerRegistrySection.tsx`         | A2A 协议与远程可信节点名册卡片：远程 Peer CRUD（名称/URL/描述/认证方式/密钥托管）、端点即时 AgentCard 探活（Probe）、SSRF 安全拦截防护、AgentCard JSON 镜像预览弹窗；响应式自适应布局                                                                                 |
| `A2AInboundApprovalSection.tsx`      | A2A 外联入站零信任审批卡片：未授权请求准入拦截、待审批请求队列呈现、Prompt 内容安全检查与一键批准/拒绝闭环；纯 Tailwind 矢量图标设计                                                                                                                                  |
| `A2APeerRegistrySection.test.tsx`    | A2A Peer Registry Section 渲染、新建、Probe 探活与状态 Badge、删除交互测试                                                                                                                                                                                            |
| `WebhookEndpointForm.tsx`            | Create/Edit 共用表单：名称、URL、Agent 范围、HMAC 密钥（Edit 留空不改）、事件多选（0 项禁用提交）                                                                                                                                                                     |
| `LifecycleWebhookSection.test.tsx`   | Webhook Section 渲染、Create/Edit 流程、Agent 范围清除（`clear_agent_scope`）、saved ping 交互测试                                                                                                                                                                    |
| `IntegrationConnectDialog.tsx`       | 目录条目连接对话框编排：API Key 凭证校验与配置组装，串联 `connect-dialog/` 的探测与安全闸门两层；探测失败的推荐动作闭环（重试成功后自动续接连接；`local_or_tauri` 打开本地部署指引并引导切换模式）；`probeUrl` 缺失时回退 `mcpConfig.url`，避免探测语义死路；连接状态覆盖安全扫描全程，按钮在扫描期间保持忙碌以防重复触发 |
| `connect-dialog/`                    | 连接对话框内部分层：探测 / 安全闸门两个 hook、诊断与认证区展示组件、流程特征化测试 · [connect-dialog/_ARCH.md](connect-dialog/_ARCH.md)                                                                                                                               |
| `deploymentGuard.ts`                 | 连接前部署模式守卫：在 cloud/sandbox 下阻断 local-only 条目（含无 probeUrl 兜底）                                                                                                                                                                                     |
| `deploymentGuard.test.ts`            | 部署守卫单测：覆盖 cloud_not_supported 在 sandbox/local-only 下的阻断决策                                                                                                                                                                                             |
| `IntegrationConnectDialog.test.tsx`  | Dialog 行为级单测：覆盖无 probeUrl 兜底阻断、probe `shouldBlockConnect=true` 阻断、`reasonCode` 文案分流，以及 `recommendedMode` 三分支动作闭环（`start_local_editor_mcp` / `verify_local_network_and_editor` 重试后自动续接连接，`local_or_tauri` 打开本地部署指引） |
| `IntegrationMemorySection.tsx`       | 集成相关记忆设置                                                                                                                                                                                                                                                      |
| `catalog-types.ts`                   | Catalog 类型定义（条目、凭证字段，以及 `mcpConfig` 的连接模板类型视图）                                                                                                                                                                                               |
| `catalog-icons.tsx`                  | Catalog 内联矢量图标（搜索、外链、勾选）                                                                                                                                                                                                                              |
| `service-icons.tsx`                  | 服务品牌图标                                                                                                                                                                                                                                                          |

## 依赖

- [integration/_ARCH.md](../_ARCH.md)
- `@/services/integrations` — 集成 REST 客户端
