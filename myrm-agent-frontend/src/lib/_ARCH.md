# lib/

## 架构概述

前端纯逻辑层：API 封装辅助、认证/部署模式、工具函数、常量。**无 React 组件**（审批可视化等见 `lib/approval/`）。

## 子模块

| 目录 / 文件 | 职责 | 文档 |
|-------------|------|------|
| `api.ts` | 通用 fetch 封装；`apiRequest` / `fetchWithTimeout` 共享本地 gate（`BACKEND_UNREACHABLE`）+ Next 代理纯文本 5xx 与 local `Failed to fetch` 归一化；`fetchWithTimeout` 另注入 mobile pair header | 内联 |
| `mobileRemote.ts` | Pair token 存储/刷新；Hub URL 构建；`withMobilePairHeaders`（Hub list + scoped 控制） | 内联 |
| `batch-optimization.ts` | 批量优化页类型、状态过滤、进度/统计聚合与格式化（无 HTTP；列表/创建在 page 直调 `apiRequest`） | 内联 |
| `deploy-mode.ts` / `auth-*.ts` / `cp-*.ts` | 部署模式、CP OAuth、沙箱 URL、Billing API 与 `BillingPlanKey` SSOT；Tauri 在 loopback dev host 走 `/api/v1` 代理 | 内联 |
| `tauri-system-config-cache.ts` | Tauri 桌面 `saveAndRestart`/`resetConfig` 前写入 `myrm-tauri-system-config` localStorage，供 `deploy-mode.ts` 冷启动读端口 | 内联 |
| `backend-health.ts` | 后端健康轮询、`fetchBackendHealth`（含 `system_status`）、`ensureLocalBackendReady` 单飞 gate（Boot 复访 fail-fast、不可达后 fast re-probe、`markLocalBackendUnreachable` 运输失败后失效缓存）、`checkBackendReadyOnce` | 内联 |
| `local-backend-dev.ts` | Boot session SSOT + health-aware local setup hint（Boot/Banner/Settings）；`resolveBackendUnreachableMessage`（api 层从 `#locales` en/zh 读取 `common.configLoadError`） | 内联 |
| `local-backend-e2e-probe.ts` | Chrome E2E tab 判定 + 私 Backend 绑定等待（Banner 抑制 shared `:8080` 误报） | 内联 |
| `locale-personal-sync.ts` | 登录后将 cookie locale 写入 `personalSettings`（对齐 Agent 消息 locale） | 内联 |
| `utils/localeUtils.ts` | `NEXT_LOCALE_COOKIE_NAME`、`parseLocaleQueryParam`、`urlWithoutLocaleParam`（middleware 营销接力） | 内联 |
| `product-surface.ts` | 隐藏 builtin agent / 未来上线前的产品面 SSOT（镜像 server `product_surface.py`） | 内联 |
| `utils/agentConfigMapper.ts` | Agent → AgentConfig 标准映射（消除多处重复映射） | 内联 |
| `utils/diagnostic-export.ts` | DoctorDashboard 诊断数据格式化（Markdown/JSON）与导出 | 内联 |
| `fonts.ts` | 全局字体系统配置（Inter/JetBrains Mono next/font 实例、字体目录 FONT_CHOICES、动态加载 ensureFontLoaded） | 内联 |
| `i18n/` | 非 React 运行时 i18n（SSE/通知；与 `src/i18n/` next-intl 路由层分离） | [_ARCH.md](i18n/_ARCH.md) |
| `metadata/` | 构建期 metadata 文案（`generateMetadata`；与运行时 locale 分离） | [_ARCH.md](metadata/_ARCH.md) |
| `diff/` | unified diff 纯函数解析 | [_ARCH.md](diff/_ARCH.md) |
| `config/` | 设置表单 schema 工具 | [_ARCH.md](config/_ARCH.md) |
| `search/` | SearXNG 预设 + Embedding/Reranker provider 目录 | [_ARCH.md](search/_ARCH.md) |
| `approval/` | 工具审批决策与 visual 上下文 | [_ARCH.md](approval/_ARCH.md) |
| `channels/` | 渠道 Ingress 静态分类与凭证判定 | [_ARCH.md](channels/_ARCH.md) |
| `intent-dispatcher/` | 意图分发 schema | [_ARCH.md](intent-dispatcher/_ARCH.md) |
| `vision/` | 语音视觉会话纯函数 | [_ARCH.md](vision/_ARCH.md) |
| `web-push/` | Web Push SW 深链 URL 消毒与 focus/navigate 判定 | [_ARCH.md](web-push/_ARCH.md) |
| `widget-theme-bridge.ts` | Artifact iframe 运行时脚本注入：主题同步、高度 sync、链接拦截、DOM 元素拾取 | 内联 |
| `constants/` | 路径、artifact、主题常量 | [_ARCH.md](constants/_ARCH.md) |
| `server/` | Next Route Handler 用 HTTP 辅助 | [_ARCH.md](server/_ARCH.md) |
| `skills/` | 技能 OAuth 展示名等纯函数 | [_ARCH.md](skills/_ARCH.md) |
| `utils/` | 跨 feature 通用工具函数 | [_ARCH.md](utils/_ARCH.md) |
| `desktop/` | 桌面权限引导深链 SSOT（Tauri / Web fallback） | [_ARCH.md](desktop/_ARCH.md) |
| `__tests__/` | lib 层单元测试 | 内联 |

## 依赖

- 不依赖 `@/components`（单向：components → lib）
- `@/lib/api` — `API_BASE_URL`、通用 fetch
- `@/lib/deploy-mode.ts` — 部署模式探测

## 约束

- 新域优先建子目录 + `_ARCH.md`（参考 `approval/`）。
- 禁止 `lib/index.ts` 桶导出；`intent-dispatcher/index.ts` 为跨域门面，见根 [_ARCH.md](../../_ARCH.md)「桶导出政策」。
