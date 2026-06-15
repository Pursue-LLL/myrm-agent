# myrm-agent-frontend 模块架构

## 架构概述

Next.js 16 WebUI。与 `myrm-agent-server` 同处 monorepo，可引用根目录 `shared/` 静态配置。

## Monorepo 构建契约

| 项 | 配置 | 说明 |
|----|------|------|
| `@shared/*` | `tsconfig.json` paths + `next.config.ts` | 指向 `../shared/*` |
| `turbopack.root` | monorepo 根（`myrm-agent/`） | dev/build 解析跨包 JSON |
| `outputFileTracingRoot` | monorepo 根 | standalone/Tauri 打包 trace |
| Docker build | [Dockerfile](Dockerfile) | builder 布局 `/app/frontend` + `/app/shared`（context = `myrm-agent/` 根） |
| CI | `frontend-build.yml` | `shared/**` 变更触发 remap vitest + line budget + `next build` |

## 脚本

| 文件 | 职责 |
|------|------|
| `scripts/check_file_line_budget.py` | TS/TSX 400 行预算 CI（baseline 在 `scripts/ci/file_line_budget_baseline.txt`） |

## 子模块

| 目录 | 文档 |
|------|------|
| `src/app/` | [src/app/_ARCH.md](src/app/_ARCH.md) |
| `src/components/` | [src/components/_ARCH.md](src/components/_ARCH.md) |
| `src/store/` | [src/store/_ARCH.md](src/store/_ARCH.md) |
| `src/lib/` | [src/lib/_ARCH.md](src/lib/_ARCH.md) |
| `src/services/` | [src/services/_ARCH.md](src/services/_ARCH.md) |
