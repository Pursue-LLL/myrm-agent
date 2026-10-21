# Chat Window Outline & Composer Fast Focus Architecture

## 1. 概述与定位
本子包位于 `myrm-agent-frontend/src/components/features/chat-window/outline/`，对标 Roadmap Item 24 (`ConversationOutlineStaircaseNavigatorAndComposerFastFocus` · P0)。
旨在彻底解决长程复杂任务中几十轮对话上下漫无目的翻找与输入焦点丢失痛点：
1. **阶梯几何学微缩大纲轨 (Staircase Scale Geometry)**：距离当前视口/悬浮引力中心越近，刻度越长越饱满，远端平滑渐近衰减，提供柔和聚焦透视感；
2. **悬停意图 Tooltip 卡片**：毫秒级浮出结构化轮次卡片（提问标题摘要、Agent 回复摘要、In-Flight 与加载状态）；
3. **Alt+↑/↓ 键盘轮次跳跃**：免除滚轮拖拽负担，键步直达上下文；
4. **Composer Fast Focus (Mod+K / Cmd+K / Ctrl+K)**：无论在文件树、Diff 面板还是终端中，一键光标瞬移至聊天输入框；
5. **长会话紧凑溢出轨**：在 50+ 轮超长对话场景下启用紧凑内置滚动，杜绝页面溢出与割裂。

## 2. 模块结构与文件表
| 文件 | 职责 |
|---|---|
| `outlineTypes.ts` | 强类型契约定义（`OutlineTurnItem`, `StaircaseGeometryItem`, `ConversationOutlineProps` 等，零 `any`） |
| `useOutlineGeometry.ts` | 阶梯缩放几何学纯计算与 Hook，依据焦点轮次计算 `scale`, `width`, `height`, `opacity` |
| `useComposerFastFocus.ts` | 全局快捷键与事件流驱动的 Composer 快速聚焦引擎 |
| `ConversationOutline.tsx` | 阶梯微缩导航轨视图组件，集成 Tooltip、ARIA a11y 与键盘轮次切换 |
| `index.ts` | 统一导出门面 |
| `__tests__/` | 核心单测套件 |

## 3. 设计红线与质量约束
- **零 any**：所有状态和属性必须使用具体 Type Hints；
- **行数控制**：单文件严格控制在 350 行以内，单一职责；
- **零原生 emoji**：图标全量使用标准 SVG 矢量组件；
- **无障碍访问**：满足 `role="navigation"`, `role="tooltip"`, `aria-current="location"`, `aria-label` 等 a11y 规范。
