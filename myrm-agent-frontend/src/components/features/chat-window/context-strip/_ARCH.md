# context-strip/

## 架构概述

输入区上方统一内联上下文胶囊流（Composer Context Chip Strip）。
作为输入框发射前（Pre-flight）所有挂载项的唯一 SSOT 视图中枢，优雅聚合显式技能激活、工作流模板、单轮能力范围、会话挂载知识库、@ 提及引用，并提供 Token 负载 Amber 警示与一键能力剪枝联动。

## 文件清单

| 文件                                                    | 地位 | 职责                                                                                                                                                                               | I/O/P |
| ------------------------------------------------------- | ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ComposerContextChipStrip.tsx`                          | 核心 | 统一内联胶囊流容器组件：桌面端最多展示 4 项、移动端最多展示 2 项，溢出项通过 Popover 抽屉展示；支持单项 `×` 移除与条目点击动作；集成 Amber Overload Nudge 按钮直接调起单轮能力面板 | ✅    |
| `__tests__/ComposerContextChipStrip.test.tsx`           | 测试 | 胶囊渲染、单项注销回调、Amber 告警按钮触发、溢出折叠与条目动作单元测试                                                                                                             | ✅    |
| `__tests__/ComposerContextChipStrip.knowledge.test.tsx` | 测试 | 会话挂载知识库（knowledge）胶囊渲染与一键解绑回调专项目标单元测试                                                                                                                  | ✅    |

## 数据契约与依赖

- 上游 Hook：`@/hooks/message-input/useComposerContextChips` 提供 `chips` 列表与 `summary` 负载信息（含会话外挂知识库 `knowledge` 类别）。
- 交互闭环：`onOpenCapabilityEditor` 联动 `TurnCapabilityToggle`，支持用户一键裁剪冗余 MCP 与技能。
- 动静分层：富媒体附件（图片/视频/文档）由 `AttachList` 专职负责缩略图与画笔批注，胶囊流专注于逻辑上下文，避免视觉重叠。
