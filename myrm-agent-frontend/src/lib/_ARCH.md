# lib/

## 架构概述

前端纯逻辑层：API 封装辅助、认证/部署模式、工具函数、常量。**无 React 组件**（审批可视化等见 `lib/approval/`）。

## 子模块

| 目录 / 文件 | 职责 | 文档 |
|-------------|------|------|
| `api.ts` | 通用 fetch 封装；`fetchWithTimeout` SSOT 注入 mobile pair header | — |
| `mobileRemote.ts` | Pair token 存储/刷新；Hub URL 构建；`withMobilePairHeaders`（Hub list + scoped 控制） | — |
| `batch-optimization.ts` | 批量优化页类型、状态过滤、进度/统计聚合与格式化（无 HTTP；列表/创建在 page 直调 `apiRequest`） | — |
| `deploy-mode.ts` / `auth-*.ts` / `cp-*.ts` | 部署模式、CP OAuth、沙箱 URL、Billing API 与 `BillingPlanKey` SSOT | — |
| `locale-personal-sync.ts` | 登录后将 cookie locale 写入 `personalSettings`（对齐 Agent 消息 locale） | — |
| `utils/localeUtils.ts` | `NEXT_LOCALE_COOKIE_NAME`、`parseLocaleQueryParam`、`urlWithoutLocaleParam`（middleware 营销接力） | — |
| `utils/agentConfigMapper.ts` | Agent → AgentConfig 标准映射（消除多处重复映射） | — |
| `utils/diagnostic-export.ts` | DoctorDashboard 诊断数据格式化（Markdown/JSON）与导出 | — |
| `utils/`（其他） | 消息、文件、URL 等工具函数 | — |
| `diff/` | unified diff 纯函数解析 | [_ARCH.md](diff/_ARCH.md) |
| `config/` | 设置表单 schema 工具 | — |
| `search/` | SearXNG 预设 + Embedding/Reranker provider 目录 | [_ARCH.md](search/_ARCH.md) |
| `approval/` | 工具审批决策与 visual 上下文 | [_ARCH.md](approval/_ARCH.md) |
| `channels/` | 渠道 Ingress 静态分类与凭证判定 | [_ARCH.md](channels/_ARCH.md) |
| `intent-dispatcher/` | 意图分发 schema | — |
| `vision/` | 语音视觉会话 | — |
| `widget-theme-bridge.ts` | Artifact iframe 运行时脚本注入：主题同步、高度 sync、链接拦截、DOM 元素拾取 | — |
| `constants/` | 路径、artifact、主题常量 | — |
| `server/` | Next Route Handler 用 HTTP 辅助 | — |
| `__tests__/` | lib 层单元测试 | — |

## 依赖

- 不依赖 `@/components`（单向：components → lib）
- `@/lib/api` — `API_BASE_URL`、通用 fetch
- `@/lib/deploy-mode.ts` — 部署模式探测

## 约束

- 新域优先建子目录 + `_ARCH.md`（参考 `approval/`）。
- 禁止 `lib/index.ts` 桶导出。
