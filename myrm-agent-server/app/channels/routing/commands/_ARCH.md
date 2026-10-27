# channels/routing/commands/

## 架构概述

IM 渠道斜杠命令解析与执行域：统一命令解析入口与各功能域命令实现（审批、停止、目标、记忆与配额状态诊断、模式交互）。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 门面 | 聚合导出，保持 `router_commands` import 稳定 | [OK] |
| `commands.py` | 模块 | 命令解析与斜杠命令执行统一入口 | [OK] |
| `router_commands.py` | 模块 | `RouterCommandsMixin`：把各命令族 mixin（approval / stop / delegation / session / modes / goals / memory / draft / quota）组合成路由器使用的单一命令处理基类 | [OK] |
| `router_commands_approval.py` | 模块 | 审批相关命令（approve/reject 等，含 reaction、按钮审批与决定恢复载荷，以及审批超时到点后的续跑 `_resume_after_approval_timeout`）；`/deny <理由>` 的理由先过入站风险闸门，被拦时审批保持待决 | [OK] |
| `router_commands_stop.py` | 模块 | `/stop` 与会话中止：`/stop` 先停前台回合（回复里写明仍在后台运行的委托任务编号），前台没有任务时再停该会话的后台委托任务（回复里写明已停止的任务编号）；`_abort_session_task`（`/stop` 与 `/new` 共用）在会话有待决审批时同时取消该聊天的审批超时计时器，停掉的会话不会被计时器之后又恢复 | [OK] |
| `router_commands_delegation.py` | 模块 | `/delegate` 后台任务的启动（回执、后台 run、并发名额）与审批交接：后台任务停在工具审批时，把审批提示发到聊天并登记为待决审批，之后的 `/approve`、`/deny`、按钮和 reaction 与前台审批走同一条路径；该会话已有进行中的前台回合时不抢占它的位置；委托任务的所属用户取 `msg.user_id or msg.sender_id`（与 `/stop`、转向一致） | [OK] |
| `router_commands_draft.py` | 模块 | 在聊天里决定被扣留的回复（`/draft approve` 或 `/draft reject` 加短码，含纯函数 `parse_draft_args`）；仅 owner 可用，经 `ApprovalRegistry.resolve_approval` 与 WebUI/按钮同一收口 | [OK] |
| `router_commands_goals.py` | 模块 | 目标（goal）相关命令；`/goal` 设定与 `/goal resume` / `/goal unwait` 之后提交 kickoff 消息让目标开始干活 | [OK] |
| `router_commands_memory.py` | 模块 | 会话状态诊断（/status）、看板与长期记忆交互（/kanban, /learn, /memory；待审批列表对纠正/遗忘提案附目标记忆摘要；目标已变化的提案以用户语言提示并保持待审，`approve all` 逐条审批并汇报未通过数量） | [OK] |
| `router_commands_modes.py` | 模块 | 模式切换命令 | [OK] |
| `router_commands_session.py` | 模块 | 会话命令：/new 清理链、/compact、/retry、/undo 委托，以及话题绑定命令（/bind、/unbind、/topic） | [OK] |
| `router_commands_quota.py` | 模块 | 配额使用诊断与本地直出（/quota）、字符进度条与动态倒计时 | [OK] |
