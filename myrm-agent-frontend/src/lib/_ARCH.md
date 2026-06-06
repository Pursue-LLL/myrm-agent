# lib/

## 架构概述

前端纯逻辑层：API 封装辅助、认证/部署模式、工具函数、常量。**无 React 组件**（审批可视化等见 `lib/approval/`）。

## 子模块

| 目录 / 文件 | 职责 | 文档 |
|-------------|------|------|
| `api.ts` | 通用 fetch 封装与错误处理 | — |
| `deploy-mode.ts` / `auth-*.ts` / `cp-*.ts` | 部署模式、CP OAuth、沙箱 URL | — |
| `locale-personal-sync.ts` | 登录后将 cookie locale 写入 `personalSettings`（对齐 Agent 消息 locale） | — |
| `utils/localeUtils.ts` | `NEXT_LOCALE_COOKIE_NAME`、`parseLocaleQueryParam`、`urlWithoutLocaleParam`（middleware 营销接力） | — |
| `utils/`（其他） | 消息、文件、URL 等工具函数 | — |
| `config/` | 设置表单 schema 工具 | — |
| `search/` | SearXNG 预设 | — |
| `approval/` | 工具审批决策与 visual 上下文 | [_ARCH.md](approval/_ARCH.md) |
| `intent-dispatcher/` | 意图分发 schema | — |
| `vision/` | 语音视觉会话 | — |
| `constants/` | 路径、artifact、主题常量 | — |
| `server/` | Next Route Handler 用 HTTP 辅助 | — |
| `__tests__/` | lib 层单元测试 | — |

## 依赖

- 不依赖 `@/components`（单向：components → lib）
- 可依赖 `@/config` 环境变量

## 约束

- 新域优先建子目录 + `_ARCH.md`（参考 `approval/`）。
- 禁止 `lib/index.ts` 桶导出。
