# commands/

## 架构概述

情境感知型渐进式能力即时推荐、交互式快捷指令全景面板与智能微引导前端模块（Item 38 P0）。
直击系统功能深度极高却「藏得太深、用户根本不知道有这功能」的学习曲线痛点。
上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `index.ts` | 入口 | 门面导出类型、状态库、建议条与指令矩阵弹窗组件 | ✅ |
| `commandMatrixTypes.ts` | 契约 | 强类型定义：`CommandCategory`、`CommandMatrixEntry`、`CapabilityHintChip`、`CommandMatrixState` | ✅ |
| `useCommandMatrixStore.ts` | 状态 | Zustand 状态管理库，支持矩阵加载、模糊检索、键盘高亮、localStorage 掌握账本持久化与推荐芯片拉取 | ✅ |
| `ContextAwareHintBar.tsx` | 视图 | 输入框上方的非侵入式轻量情境建议条，一键快速填入 Prompt 或执行，支持主动忽略与沉淀 | ✅ |
| `CommandMatrixModal.tsx` | 视图 | 语义 `<dialog open>` 全景分类指令面板（“鼠标垫视图”），支持 `Cmd/Ctrl + /` 呼出，五大分类 Tabs，键盘上下键选择，一键填入 | ✅ |
| `palette/` | 核心 | 全局模糊命令面板（Cmd+K / Ctrl+K）、旋转式场景占位符引擎与底栏实时性能仪表盘套件（Item 64 P0） | [palette/_ARCH.md](palette/_ARCH.md) |

## 依赖

- `next-intl` — 国际化词条 `commandMatrix`
- `lucide-react` — 矢量图标
- `zustand` — 客户端轻量状态管理
