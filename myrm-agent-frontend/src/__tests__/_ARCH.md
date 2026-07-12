# __tests__/ 模块架构

## 架构概述

Vitest 全局测试基础设施与**跨模块集成测试**入口。`setup.ts` 由 `vitest.config.ts` 的 `setupFiles` 加载。域内单元测试优先放在各模块旁的 `__tests__/`（colocated），本目录仅放不便归属单一模块的测试。

## 文件清单

| 路径 | 职责 |
|------|------|
| `setup.ts` | 全局 mock、`@testing-library/jest-dom`、环境桩 |
| `middleware.locale-relay.test.ts` | 根 `middleware.ts` locale cookie 接力 |
| `config-sync/` | `ConfigSyncManager` 跨端同步 |
| `cron/` | Cron 创建与投递 UI 契约 |
| `hooks/` | 无对应 hook 文件的纯函数测试 |
| `intent-dispatcher/` | `lib/intent-dispatcher` schema |
| `store/` | 根级 store（`useFlowPadStore`、`useMemoryStore` 等） |
| `tauri-mode/` | Tauri 运行时分支（`AttachButton`、`ImagePreview`） |
| `vision/` | 多模态 / 语音视觉管线 |

## 测试组织约定

| 模式 | 位置 | 适用 |
|------|------|------|
| Colocated | `src/**/__tests__/*` | **默认**：与被测模块同目录 |
| 中央集成 | `src/__tests__/*` | 跨层或 middleware / 平台分支 |

禁止邻接 `*.test.ts(x)` 与源文件同目录；新测试仅使用上表两种模式。

## 依赖

- `vitest.config.ts` — alias `@`、`@shared`、`#locales`
- `bun run verify:i18n` — `pretest` 门禁

## 约束

- 禁止仓根 `tests/` 目录与 Playwright/puppeteer E2E
- 新测试优先 colocated，避免膨胀本目录
