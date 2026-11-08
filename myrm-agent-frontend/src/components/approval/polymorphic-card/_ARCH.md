# approval/polymorphic-card/

## 架构概述

`PolymorphicApprovalCard` 的组成部分：按审批动作类型选择评审正文，从每个工具的评审配置派生风险标记，并持有 shell 编辑与「始终允许」的选择状态。入口组件留在上一级目录，只负责把这些部分串起来。

## 文件清单

| 文件                           | 地位 | 职责                                                                                                                                                                                                                                                                    |
| ------------------------------ | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `types.ts`                     | 类型 | `ApprovalResolveHandler`（决定回调：动作、评论、编辑后的 payload 与授权/引导等附加字段）、`DrawerDecisionAction`                                                                                                                                                        |
| `approvalFlags.ts`             | 辅助 | `deriveApprovalFlags`：从 payload 与 `reviewConfigs` 派生展示与决策所需的标记（被安全评审拒绝、auto mode 暂停及触发的限额、社交不可逆、不可逆破坏及其爆炸半径与快照、是否不提供「始终允许」、花费配置）；配置畸形时降级为「无标记」而不抛错                             |
| `useAllowAlwaysChoice.ts`      | Hook | 「始终允许」的范围与时长；每条新审批（或换工具）时范围回到该工具的默认值，时长保留                                                                                                                                                                                      |
| `useShellEdit.ts`              | Hook | 只含一条 shell 调用的 subagent 审批的编辑：可编辑的调用与参数、编辑字段、JSON 校验（形似 JSON 却解析失败的字段拒绝提交并点名）、决定（无改动 → 批准，有改动 → 合并回原参数后以「编辑」放行）；取消编辑保留已输入内容，确认后范围与时长回到默认                          |
| `ApprovalContent.tsx`          | 核心 | 评审正文分发：按 `action_type` 选择下列内容组件；记忆更新与未知动作以文本块展示                                                                                                                                                                                         |
| `SubagentApprovalContent.tsx`  | UI   | subagent 的工具调用清单，每条按形态选择呈现：本地文件写（compact 行，语言取自路径）→ shell → save_skill 预览 → 原始参数                                                                                                                                                 |
| `ShellToolCallApproval.tsx`    | UI   | shell / 代码执行调用：执行意图、范围说明、沙箱升级命令（原因取自 `toolApproval.escalationReasons.*`，未知原因原样显示）与带风险标注的命令                                                                                                                               |
| `SkillApprovalContent.tsx`     | UI   | 技能草稿 / 补丁：原因与可展开的内容，有原文时以 diff 展示                                                                                                                                                                                                               |
| `ToolClarificationContent.tsx` | UI   | 失败工具调用的错误与参数编辑器（批准即以编辑后的 JSON 重试）；无原因时显示 `toolApproval.toolExecutionFailed`                                                                                                                                                           |
| `KnowledgePatchContent.tsx`    | UI   | 知识补丁：目标类型、置信度、触发条件、内容、依据与来源查询                                                                                                                                                                                                              |
| `BatchCostApprovalContent.tsx` | UI   | 批量子任务的费用预估：预估费用、任务数、剩余预算、运行模式与任务清单                                                                                                                                                                                                    |
| `HighRiskDomActionContent.tsx` | UI   | 高危浏览器 / 桌面 UI 动作：目标元素、按键、证据截图、将执行的动作或 JS 表达式；警告文字一律用 `text-destructive-text`                                                                                                                                                   |
| `McpElicitationContent.tsx`    | UI   | MCP 服务器向用户索取输入：来源、消息与所需字段                                                                                                                                                                                                                          |
| `ApprovalBanners.tsx`          | UI   | 四种横幅：花费保护、auto mode 暂停、社交不可逆、被安全评审拒绝                                                                                                                                                                                                          |
| `ApprovalActions.tsx`          | UI   | 拒绝 / 编辑 / 始终允许 / 批准按钮；被拒绝的动作只给「拒绝」与「仅这一次放行」；不可逆破坏在用户确认前保持锁定，批准后弹出 10 分钟的撤销卡                                                                                                                               |
| `ApprovalMetaBar.tsx`          | UI   | 审批上方的条：回到来源会话与剩余时间                                                                                                                                                                                                                                    |
| `ExpiryCountdown.tsx`          | UI   | 审批剩余时间倒计时（每秒刷新；不足一分钟转琥珀色，过期用 `text-destructive-text`）                                                                                                                                                                                      |
| `languageFromPath.ts`          | 辅助 | 文件路径 → Monaco 语言 id；未知扩展名为纯文本，空路径为 markdown                                                                                                                                                                                                        |
| `__tests__/`                   | 测试 | 各模块单测（标记派生、语言映射、倒计时、元信息条、横幅、按钮矩阵与撤销卡、两个 Hook、内容分发与各内容组件）与入口组件串联测试（`PolymorphicApprovalCard.wiring`：横幅、评论、shell 编辑流程、始终允许对话框、权限类型标签）；`approvalKit` / `approvalStubs` 为共用夹具 |

## 依赖

- `@/lib/approval/*` — 决定、授权范围、shell 命令展示的纯函数
- `@/components/approval/*` — 兄弟组件（撤销卡、确认横幅、证据截图、文件写行、范围说明等）
- `@/components/features/chat-window/approval/*` — 编辑视图与「始终允许」对话框（由入口组件使用）
