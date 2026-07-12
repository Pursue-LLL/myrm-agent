# myrm-agent-frontend 架构

## 概述

Next.js 16 WebUI（local :3000、Tauri WebView、云托管沙箱）。业务后端为同 monorepo 的 `myrm-agent-server`；**不含**多租户控制平面逻辑。

## 分层

| 层 | 路径 | 职责 |
|----|------|------|
| 路由壳 | `src/app/` | App Router 薄页面 |
| UI | `src/components/` | `layout/`、`primitives/`、`features/` |
| 状态 | `src/store/` | Zustand |
| 副作用 | `src/hooks/` | React hooks |
| API 客户端 | `src/services/` | REST/SSE 类型化客户端 |
| 纯逻辑 | `src/lib/` | 无 React 工具与常量 |
| i18n | `src/i18n/` + 根 `locales/` | next-intl 与文案 SSOT |
| 共享类型 | `src/types/` | 跨 feature 类型 |
| 测试基建 | `src/__tests__/` | Vitest setup 与跨模块集成测；域内单测 colocated 于 `src/**/__tests__/` |
| 边缘路由 | `src/middleware.ts` | locale cookie 接力 |

依赖方向：`app/components → hooks/store/services/lib`，禁止反向。

## Monorepo

- `@shared/*` → `../shared/*`
- 构建：`turbopack.root` / `outputFileTracingRoot` 指向 `myrm-agent/`
- 详见 [_ARCH.md](_ARCH.md)

## 文档导航

模块级说明使用分形 [_ARCH.md](_ARCH.md) 索引；开发脚本见 [scripts/_ARCH.md](scripts/_ARCH.md)。

## 质量门禁

- `scripts/check_fractal_docs.py` — 目录必须有 `_ARCH.md`
- `scripts/check_file_line_budget.py` — 新文件 ≤400 行
- `scripts/check_barrel_exports.py` — 跨域 `index.ts` 桶导出白名单
- `bun run test` — Vitest；WebUI E2E 走 MCP chrome-devtools（禁止 Playwright 无头）
