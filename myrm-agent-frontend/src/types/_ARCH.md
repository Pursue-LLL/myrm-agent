# types/ 模块架构

## 架构概述

跨 feature 共享的 TypeScript 类型与全局 ambient 声明。域专属类型优先放在对应 `store/` 或 `components/features/` 子目录。

## 文件清单

| 文件 | 职责 |
|------|------|
| `system.ts` | Tauri / 桌面系统配置（对齐 Rust `SystemConfig`） |
| `artifact.ts` | 工件门户与预览类型 |
| `channels.ts` | 渠道配置 UI 类型 |
| `command.ts` | Slash 命令与内置行为类型 |
| `presetAgent.ts` | 预置 Agent 模板类型 |
| `globals.d.ts` | 全局 ambient（Window 扩展等） |

## 依赖

- `@/services/*` — API 响应映射
- `@/store/*` — 部分 store 再导出类型

## 约束

- 禁止 `any`；与 server Pydantic schema 变更时同步更新
