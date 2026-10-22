# task-action-preview/

## 架构概述

本模块实现对话建议智能脱敏清洗转 Task（智能去除前置/后置寒暄客套、提炼纯净动宾标题并回填任务草稿）以及高危操作 Typed Action 范围预览模态框（展示动作类型、受影响文件范围、配额变更差异、潜在副作用与显式安全门限）和执行后生成的不可篡改操作回执卡（带时间戳与 SHA 密码学签名）。对标 LoopX 智能任务提取与先预览后确认安全模型精髓。

## 文件组织

| 文件 | 地位 | 职责 | I/O/P |
| --- | --- | --- | --- |
| `taskActionPreviewTypes.ts` | Types | 核心数据模型契约（CleanedActionItem, TypedActionPayload, ImmutableOperationReceipt） | [INPUT] 无外部运行时依赖<br>[OUTPUT] 动作清洗、高危操作预览与回执数据契约<br>[POS] 任务操作类型事实源 |
| `smartFluffStripper.ts` | Logic | 本地轻量废话剥离与动宾行动项提炼算法 | [INPUT] 原始对话建议字符串<br>[OUTPUT] 纯净动宾行动项 CleanedActionItem<br>[POS] 前端智能文本清洗核心算法 |
| `SmartTaskExtractionButton.tsx` | UI | 一键「转为 Task」智能清洗与草稿分发按钮组件 | [INPUT] smartFluffStripper, taskActionPreviewTypes<br>[OUTPUT] 智能任务提取触发按钮与回调<br>[POS] 消息气泡底栏快捷操作入口 |
| `TypedActionPreviewModal.tsx` | UI | 受保护高危操作类型化范围预览与安全确认门限模态框 | [INPUT] TypedActionPayload<br>[OUTPUT] 范围预览、副作用警示与安全确认对话框<br>[POS] 高危动作执行前安全防护门限 |
| `OperationReceiptBadge.tsx` | UI | 不可篡改操作回执卡片与密码学 SHA 签名审计组件 | [INPUT] ImmutableOperationReceipt<br>[OUTPUT] 可折叠审计回执徽章卡片<br>[POS] 高危操作执行后留痕呈现 |
| `index.ts` | Facade | 门面统一导出 | [INPUT] 内部所有子模块<br>[OUTPUT] 统一对外导出公共 API<br>[POS] 模块对外唯一门面 |
