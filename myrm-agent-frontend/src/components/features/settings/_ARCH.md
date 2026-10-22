# settings 模块架构

## 架构概述

设置页壳层：`SettingsLayout`（URL 为唯一数据源 + Section 缓存）、`SettingsMenu`（分组导航）、共享表单 primitive。Tab 预加载由 Next.js partial prefetch 与 `next/dynamic` 承担。

### Settings 路由 SSOT

| 层级                  | URL 形态                | 示例                                 | 实现                                                                                                                    |
| --------------------- | ----------------------- | ------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| **Index redirect**    | `/settings`             | → `/settings/account`                | `app/settings/page.tsx` server `redirect()` — 禁止无 tab 挂载 `SettingsLayout`                                          |
| **顶层 Tab**          | `/settings/[tab]`       | `/settings/wiki`、`/settings/memory` | `settingsRoutes.ts` `SETTINGS_TABS` 登记合法 id；`SettingsLayout.tsx` `handleTabChange` → `` `/settings/${tab}` ``，`urlTab` 读 `params.tab` 并以 `SETTINGS_TABS` 校验 |
| **Section 子视图**    | `/settings/[tab]?sub=`  | `/settings/memory?sub=migration`     | `SettingsLayout.tsx` `handleTabChange(tab, sub)`                                                                        |
| **别名路由**          | `/settings/<alias>`     | `/settings/persona` → `/settings/personalization` | `settingsRoutes.ts` `SETTINGS_TAB_REDIRECTS`，由 `app/settings/[tab]/page.tsx` 服务端 `redirect()` 消化，别名 id 不会进入 `SettingsLayout` |
| **Memory 内部子 Tab** | `/settings/memory?tab=` | `/settings/memory?tab=shared`        | Memory Section 专用 query（如 `memoryOperationToasts.ts`）                                                              |

**禁止**使用已废弃的顶层 query 形态 `/settings?tab=wiki`。Wiki agent 作用域深链为 `/settings/wiki?agentId=<id>`（见 `sections/knowledge/_ARCH.md`）。代码、后端推送与预置技能资产里写死的 `/settings/<tab>` 深链必须落在 `SETTINGS_TABS` 或 `SETTINGS_TAB_REDIRECTS` 内，由 `myrm-agent-server/tests/architecture/test_settings_deep_links.py` 守门。

## 核心文件

| 文件                                                                               | 地位 | 职责                                                                         | I/O/P |
| ---------------------------------------------------------------------------------- | ---- | ---------------------------------------------------------------------------- | ----- |
| `settingsRoutes.ts`                                                                | 核心 | 路由 SSOT：Tab id、别名重定向、仅桌面端 Tab；page / Layout / Menu / 脏状态 store / `verify-i18n` / 后端深链架构测试共读 | ✅    |
| `SettingsLayout.tsx`                                                               | 核心 | Tab 路由、动态加载 Section、脏状态守卫                                       | ✅    |
| `SettingsMenu.tsx`                                                                 | 核心 | 分组侧栏（personal / ai-core / ai-tools / knowledge / integration / system） | ✅    |
| `FormFields.tsx`                                                                   | 辅助 | 通用表单字段                                                                 | ✅    |
| `SchemaForm.tsx`                                                                   | 辅助 | JSON Schema 驱动表单                                                         | ✅    |
| `ConfigImportExport.tsx`                                                           | 辅助 | 配置导入导出                                                                 | ✅    |
| `MCPConfigForm.tsx`                                                                | 辅助 | MCP 顶层表单（详情见 `mcp/`）                                                | ✅    |
| `Switcher.tsx`                                                                     | 辅助 | 亮/暗/系统主题切换                                                           | ✅    |
| `AppearancePanel`（`theme/AppearancePanel.tsx`）                                   | 辅助 | Theme Engine v2 预设、壁纸上传、wash 滑条、字体（ConfigSync SSOT）           | ✅    |
| `ThemeStudioSettingsSection`（`sections/personal/ThemeStudioSettingsSection.tsx`） | 辅助 | 四步 Theme Studio 设置页 `/settings/theme-studio`                            | ✅    |

## 子目录

| 目录                             | 职责                                                 | 文档                                                                             |
| -------------------------------- | ---------------------------------------------------- | -------------------------------------------------------------------------------- |
| `sections/`                      | 各设置 Tab 的 Section 组件（六组子目录）             | [sections/_ARCH.md](sections/_ARCH.md)                                           |
| `sections/integration/`          | 集成域 Section（扩展桥、凭证、外部 Agent、通信容器） | [sections/integration/_ARCH.md](sections/integration/_ARCH.md)                   |
| `sections/integration/channels/` | 渠道、路由、语音配置卡片                             | [sections/integration/channels/_ARCH.md](sections/integration/channels/_ARCH.md) |
| `sections/knowledge/wiki/`       | Wiki 设置                                            | [sections/knowledge/wiki/_ARCH.md](sections/knowledge/wiki/_ARCH.md)             |
| `mcp/`                           | MCP 列表/编辑/安全扫描 Ack                           | [mcp/_ARCH.md](mcp/_ARCH.md)                                                     |
| `common/`                        | 骨架屏、共享 UI                                      | [common/_ARCH.md](common/_ARCH.md)                                               |
| `default-model/`                 | 默认模型子表单                                       | [default-model/_ARCH.md](default-model/_ARCH.md)                                 |
| `model-overrides/`               | 用户自定义模型 Context 窗口、输出上限与 BYOK 价格覆盖 | [model-overrides/_ARCH.md](model-overrides/_ARCH.md)                             |
| `model-service/`                 | 模型服务配置                                         | [model-service/_ARCH.md](model-service/_ARCH.md)                                 |
| `retrieval/`                     | 检索服务配置                                         | [retrieval/_ARCH.md](retrieval/_ARCH.md)                                         |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
