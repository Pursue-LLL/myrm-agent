# lib/progression 模块架构

---

## 架构概述

前端被动里程碑触发工具层。提供幂等的 milestone 触发函数，供 store handler 和 hook 调用。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `tryMarkMilestone.ts` | 核心 | 幂等触发 milestone + level-up toast | ✅ |

---

## 依赖

### 内部依赖
- `@/store/useProgressionStore` — 进度状态 store（POS: 用户能力进度状态管理）
- `@/lib/utils/toast` — toast 通知工具

### 被依赖方
- `completionEvents.ts`（MESSAGE_END 时触发 first_chat/first_tool_use）
- `useToolApprovalResolve.ts`（approve 成功后触发 first_approval）
