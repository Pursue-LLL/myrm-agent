# services/commands/

## 架构概述

前端 Slash 命令服务层。为 WebUI / 桌面端的斜杠命令（`/loop`、`/goal`、`/compact`、`/focus`、`/yolo`、`/freeze`）提供参数解析、客户端预检、后端 API 调用与即时反馈编排。`store/builtinActions.ts` 的注册表只保留命令元数据，执行体经动态 import 从本目录按需加载。

## 模块结构

| 模块                                      | 职责                                                                                                                                                                                                                                                                                                                                                                                                                              |
| :---------------------------------------- | :-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `loopSlashCommand.ts`                     | 原生 `/loop` Slash 命令执行服务：中英文自然语言周期与参数解析（支持 `--interval`、`--times`、`--until`、自然语言单位及 `status` / `stop` 子命令）、会话上下文校验、联动 `sessionLoop` 客户端触发会话级自适应循环调度（`POST /chats/{chat_id}/loop/start`、`POST /chats/{chat_id}/loop/stop` 与 `GET /chats/{chat_id}/loop/status`）、广播 `session-loop-changed` 浏览器事件驱动前台状态胶囊即时同步与 Toast 回显                  |
| `goalSlashCommand.ts`                     | 原生 `/goal` Slash 命令执行服务：设置长期目标（流式生成中拒绝并提示），以及 `status` / `pause` / `resume` / `clear` 子命令；暂停、恢复、取消经 `goalActionClient` 发出，目标仍在收尾上一步时给出专门提示而非报错。行为测试见 `store/__tests__/builtinActions.goal.test.ts`                                                                                                                                                        |
| `contextSlashCommands.ts`                 | 会话上下文体量命令：`/compact [主题]` 调用 `contextCompaction::runManualCompaction` 压缩（store 同步在其中完成，不重载消息），没压缩时按 `describeCompactSkip` 的本地化措辞与严重度提示（原因原文不进界面；失败类与请求抛错一样返回 `success: false`，输入框里的命令保留以便重发），未设置 `dontRemindCompact` 时先提示手动压缩会清除 Prompt Cache；`/focus` 先停止当前回合再清空聊天记录，成功后重置会话状态并重载，保留沙箱环境 |
| `securitySlashCommands.ts`                | 改变安全姿态的命令：`/yolo [on\|off\|<时长>]` 切换 YOLO 模式（时长支持 `s` / `m` / `h`，无法识别的参数回退为切换，写回安全配置时保留其余设置）；`/freeze [off\|resume]` 经 `/security/estop` 激活或解除紧急停止，成功后广播 `estop-changed`                                                                                                                                                                                       |
| `__tests__/loopSlashCommand.test.ts`      | 针对自然语言时间解析、入参拆解、流式生成阻断防御、会话校验、status 状态查询与 SessionLoop 启停联动的全面单元测试                                                                                                                                                                                                                                                                                                                  |
| `__tests__/contextSlashCommands.test.ts`  | 压缩的聚焦主题解析、成功不重载消息、没压缩按原因（无需 / 进行中 / 暂停）措辞、服务端返回的失败与请求抛错同样按失败处理、Prompt Cache 提示开关；清空前先停止回合、成功后重置会话、失败时保持原状                                                                                                                                                                                                                      |
| `__tests__/securitySlashCommands.test.ts` | YOLO 切换 / 显式开关 / 时长换算 / 保留其余设置 / 配置未加载；紧急停止的激活、解除、失败与事件广播                                                                                                                                                                                                                                                                                                                                 |

## 约束与规范

1. **零 Token 损耗**：命令解析与预检完全在客户端完成，不注入额外系统提示词，底线保护 Prompt Cache 命中率。
2. **多语言与防御性**：所有 Toast 提示均通过 `i18nToastService` 输出；针对空 Prompt、流式中调用以及 <1m 极端间隔进行完备规整与防御。
