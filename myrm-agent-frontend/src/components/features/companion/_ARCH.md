# Companion Module — 前端宠物伴侣系统

## 架构概述

纯前端宠物伴侣系统，提供两层视觉渲染：

1. **SVG/Emoji 层**（默认）：基于 CompanionIcons 的 15 物种 + 9 帽子 SVG 渲染，随智能体切换联动，嵌入输入框旁。
2. **Sprite 层**（可选）：Canvas 2D 精灵图渲染引擎，支持 Codex 标准 8×9 SpriteSheet（1536×1872px），以可拖拽悬浮窗形式显示在屏幕上。Tauri 桌面端支持原生透明置顶窗口。

状态由 Zustand store (`useCompanionStore`) 管理，持久化至 localStorage，sprite 配置同步至服务端（跨设备同步）。

## 文件清单

| 文件                    | 地位 | 职责                                                                            |
| ----------------------- | ---- | ------------------------------------------------------------------------------- |
| `companionGenerator.ts` | 核心 | 基于 userId 的确定性伴侣生成（物种/稀有度/属性/帽子）、进化检查、情绪计算纯函数 |
| `companionAssets.ts`    | 辅助 | 物种元数据注册表（标签/描述）                                                   |
| `CompanionIcons.tsx`    | 核心 | 15 物种 + 9 帽子的 SVG React 组件，支持 `currentColor` 主题适配                 |
| `CompanionSprite.tsx`   | 核心 | 伴侣视觉渲染组件（SVG 图标、稀有度光环、状态表情、情绪动画）                    |
| `CompanionWidget.tsx`   | 核心 | 主容器组件（InfoCard、SnackButton、HoverCard、Observer、情绪计算编排）          |
| `CompanionBubble.tsx`   | 辅助 | 气泡对话框组件（思考/观察者反应/完成提示）                                      |
| `CompanionSettings.tsx` | 辅助 | 伴侣设置面板（Tab 切换：设置/图鉴，名称/物种/帽子/主题/精灵图自定义）           |
| `PetGallery.tsx`        | 辅助 | Petdex 社区宠物图鉴画廊（manifest 获取、搜索过滤、渐进加载、IntersectionObserver 懒缩略图） |
| `CompanionXpBar.tsx`    | 辅助 | XP 进度条组件                                                                   |

## sprite/ — 精灵图渲染子模块

| 文件                  | 地位 | 职责                                                                            |
| --------------------- | ---- | ------------------------------------------------------------------------------- |
| `SpriteEngine.ts`     | 核心 | Canvas 2D 精灵图渲染引擎（Codex 标准 8×9 atlas，rAF 驱动，缺帧降级）           |
| `PetStateMachine.ts`  | 核心 | 事件→动画行映射状态机（transient/sticky/release 模式，心跳超时→idle）            |
| `petStateMapping.ts`  | 核心 | 动态行序映射（Codex/Legacy 标准 + STATE\_ALIASES 别名解析 → resolveAnimRow()）  |
| `SpriteRenderer.tsx`  | 核心 | SpriteEngine 的 React 封装（Canvas 生命周期、加载态降级占位、行数检测回调）     |
| `PetOverlay.tsx`      | 核心 | 可拖拽悬浮容器（右键菜单、尺寸调节、位置记忆、SSE 事件监听、动态行序映射注入） |
| `tauriPetBridge.ts`   | 辅助 | Tauri IPC 桥接（show/hide/setRow，非 Tauri 环境静默 no-op）                     |

## 模块依赖

- `@/store/useCompanionStore` — 全局状态管理（持久化 + 会话态 + 精灵图配置）
- `@/store/useAuthStore` — 用户 ID（用于确定性生成种子）
- `@/store/useChatStore` — 消息流（Observer 反应触发、loading 状态驱动精灵动画）
- `@/store/chat/goals/useGoalStore` — 目标状态（情绪/庆祝触发）
- `next-intl` — i18n（companion.\* 键命名空间）
- `@/components/primitives/hover-card` — InfoCard 悬浮卡片
