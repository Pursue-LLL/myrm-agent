# Companion Module — 前端宠物伴侣系统

## 架构概述

纯前端宠物伴侣系统，提供 SVG 物种/帽子渲染、稀有度进化、情绪系统、零食奖励、观察者反应等能力。状态由 Zustand store (`useCompanionStore`) 管理，持久化至 localStorage。

## 文件清单

| 文件                    | 地位 | 职责                                                                            |
| ----------------------- | ---- | ------------------------------------------------------------------------------- |
| `companionGenerator.ts` | 核心 | 基于 userId 的确定性伴侣生成（物种/稀有度/属性/帽子）、进化检查、情绪计算纯函数 |
| `companionAssets.ts`    | 辅助 | 物种元数据注册表（标签/描述）                                                   |
| `CompanionIcons.tsx`    | 核心 | 15 物种 + 9 帽子的 SVG React 组件，支持 `currentColor` 主题适配                 |
| `CompanionSprite.tsx`   | 核心 | 伴侣视觉渲染组件（SVG 图标、稀有度光环、状态表情、情绪动画）                    |
| `CompanionWidget.tsx`   | 核心 | 主容器组件（InfoCard、SnackButton、HoverCard、Observer、情绪计算编排）          |
| `CompanionBubble.tsx`   | 辅助 | 气泡对话框组件（思考/观察者反应/完成提示）                                      |
| `CompanionSettings.tsx` | 辅助 | 伴侣设置面板（名称/物种/帽子/主题自定义）                                       |
| `CompanionXpBar.tsx`    | 辅助 | XP 进度条组件                                                                   |

## 模块依赖

- `@/store/useCompanionStore` — 全局状态管理（持久化 + 会话态）
- `@/store/useAuthStore` — 用户 ID（用于确定性生成种子）
- `@/store/useChatStore` — 消息流（Observer 反应触发）
- `@/store/chat/goals/useGoalStore` — 目标状态（情绪/庆祝触发）
- `next-intl` — i18n（companion.\* 键命名空间）
- `@/components/ui/hover-card` — InfoCard 悬浮卡片
