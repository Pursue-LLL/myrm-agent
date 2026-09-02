# services/commands/

## 架构概述

前端 Slash 命令服务层。为 WebUI / 桌面端各种斜杠命令（如 `/loop`）提供参数解析、客户端预检、后端 API 调用与即时反馈编排。

## 模块结构

| 模块 | 职责 |
| :--- | :--- |
| `loopSlashCommand.ts` | 原生 `/loop` Slash 命令执行服务：中英文自然语言周期解析（`s/m/h/d/分钟/小时/天/半小时/每隔` 等）、`chatId` 与 `agentId` 上下文绑定、`POST /cron` 任务持久化与 `POST /cron/{id}/trigger` 即时首跑触发 |
| `__tests__/loopSlashCommand.test.ts` | 针对自然语言时间解析、入参拆解、流式生成阻断防御、API 联动与即时首跑的全面单元测试 |

## 约束与规范

1. **零 Token 损耗**：命令解析与预检完全在客户端完成，不注入额外系统提示词，底线保护 Prompt Cache 命中率。
2. **多语言与防御性**：所有 Toast 提示均通过 `i18nToastService` 输出；针对空 Prompt、流式中调用以及 <1m 极端间隔进行完备规整与防御。
