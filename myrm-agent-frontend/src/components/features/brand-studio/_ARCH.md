# brand-studio/

## 架构概述

品牌风格记忆板：在 Settings 中提供可编辑的品牌身份表单（配色 / 字体 / 语气 / 禁忌），
品牌字段以 `brand_*` 前缀存储为 profile 记忆，经框架稳定层自动注入 agent 上下文，
使 AI 生成的交付物符合用户品牌。纯前端，复用现有 profile 记忆 API，无后端改动。

## 文件清单

| 文件                                         | 地位 | 职责                                                                 | I/O/P |
| -------------------------------------------- | ---- | -------------------------------------------------------------------- | ----- |
| `BrandStudioSection.tsx`                     | 核心 | 品牌编辑面板：字段表单 / 实时预览 / 保存 / 清空                      | ✅    |
| `brandSchema.ts`                             | 辅助 | 纯函数：`brand_*` key 映射 / 字段校验 / 预览值提取（无 I/O，可单测） | ✅    |
| `__tests__/brandSchema.test.ts`              | 测试 | brandSchema 纯函数单元测试                                           | ✅    |
| `__tests__/BrandStudioResetConfirm.test.tsx` | 测试 | 清空二次确认交互（取消保留 / 确认清空并删除）jsdom 单测              | ✅    |

## 依赖

- `@/services/memory` — `getMemories` / `createMemory` / `deleteMemory` / `Memory` / `CreateMemoryRequest` 类型
- `@/components/primitives/*` — Card / Input / Textarea / Label / Button
- `@/components/features/app-shell/confirm-dialog` — `ConfirmDialog`（清空表单前二次确认）
- `@/components/features/icons/PremiumIcons` — 图标
- 父模块 [`settings/sections/knowledge/_ARCH.md`](../../settings/sections/knowledge/_ARCH.md)

## 说明

- 品牌字段 key 统一以 `brand_` 前缀（见 `brandSchema.ts`），避免与普通 profile 记忆冲突。
- 存储即 profile 记忆：保存时对空字段执行删除，非空字段执行 upsert；agent 会话首帧稳定注入。
- 「清空表单」是破坏性操作（清空后保存会删除已配置的品牌字段），通过 `ConfirmDialog`（destructive）二次确认，防止误删。
- 界面文案仅面向终端用户，不泄漏 `brand_*` / profile / stable 层等技术细节。
