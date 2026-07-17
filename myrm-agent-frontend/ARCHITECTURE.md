# myrm-agent-frontend 架构

> **SSOT**：模块索引、CI 门禁、桶导出政策见 [**_ARCH.md**](_ARCH.md)。本文仅保留一页式分层速览。

## 分层

| 层 | 路径 | 职责 |
|----|------|------|
| 路由壳 | `src/app/` | App Router 薄页面 |
| UI | `src/components/` | `layout/`、`primitives/`、`features/` |
| 状态 | `src/store/` | Zustand |
| 副作用 | `src/hooks/` | React hooks |
| API 客户端 | `src/services/` | REST/SSE 类型化客户端 |
| 纯逻辑 | `src/lib/` | 无 React 工具与常量 |
| i18n | `src/i18n/` + 根 `locales/` | next-intl；`locales/*.json` 为 SSOT |
| 共享类型 | `src/types/` | 跨 feature 类型 |
| 测试基建 | `src/__tests__/` | Vitest setup 与跨模块集成测 |

依赖方向：`app/components → hooks/store/services/lib`，禁止反向。

## 文档与脚本

- 分形模块文档：各目录 `_ARCH.md`（由 `scripts/check_fractal_docs.py` 门禁）
- 开发/CI 脚本：[scripts/_ARCH.md](scripts/_ARCH.md)

## 质量门禁

- `scripts/check_fractal_docs.py` — 目录 `_ARCH.md`
- `scripts/check_file_line_budget.py` — 新 TS/TSX ≤400 行
- `scripts/check_typescript_strict.py` — `tsc --noEmit` 错误数不回升（baseline 见 `scripts/ci/typescript_strict_baseline.txt`）
- `scripts/check_barrel_exports.py` — 跨域 barrel 白名单
- `scripts/verify-sw-push.mjs` — `public/sw.js` 含 Web Push handler（`bun run build` 后 Serwist 编译 + CI）
- `bun run test` / `verify:i18n` — Vitest 与 i18n
