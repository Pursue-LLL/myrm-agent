# omni-reference 特性模块

## 架构概述

全域多维上下文 `@` 智能补全引用、历史会话/工件/任务穿透溯源与 Claude Code 风格生产力套件。打破输入框 `@` 只能选本地文件的狭隘边界，覆盖 `@file:`, `@session:`, `@artifact:`, `@agent:`, `@task:` 全场景对象精准引用与动态切片展开。

上级文档：[../_ARCH.md](../_ARCH.md)。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `omniReferenceTypes.ts` | 核心 | 五维目标类型（`file`, `session`, `artifact`, `agent`, `task`）、切片模型与 Store 状态契约（零 any） | ✅ |
| `useOmniReferenceStore.ts` | 核心 | 状态机（输入框唤起、搜索防抖、5 维 Tab 过滤、键盘上下方向键导航、切片提取缓存） | ✅ |
| `OmniReferenceMenu.tsx` | 核心 | `<dialog>` 语义化悬浮补全浮层（分层维度筛选、候选项渲染、键盘操作与无障碍 a11y） | ✅ |
| `OmniReferenceChip.tsx` | 核心 | 语义化可点击溯源芯片（五维图标渲染、切片 Popover 预览与 `myrm://` 血缘直达链接） | ✅ |
| `index.ts` | 门面 | 对外 re-export 公共 API | ✅ |

---

## 依赖关系

- 后端 API：`GET /api/v1/context/reference/search`, `POST /api/v1/context/reference/slice`
- 图标库：`lucide-react`（全量矢量 SVG，零原生 emoji）
- 国际化：`omniReference` 命名空间
- 状态库：`zustand`
