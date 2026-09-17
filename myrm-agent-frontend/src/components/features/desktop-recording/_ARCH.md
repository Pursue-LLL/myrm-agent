# desktop-recording/

## 架构概述

桌面工作流技能录制：把用户在桌面端的操作步骤录制成技能草稿。抽屉浮层承载录制控制、步骤列表与技能草稿编辑，状态由 `useDesktopRecordingStore` 统一管理。

## 文件清单

| 文件                         | 地位 | 职责                                                       | I/O/P |
| ---------------------------- | ---- | ---------------------------------------------------------- | ----- |
| `DesktopRecordingDrawer.tsx` | 核心 | 录制抽屉：开始/停止录制、步骤列表增删、草稿合成与发布技能   | ✅    |

## 依赖

- `@/store/useDesktopRecordingStore`（POS: 桌面录制状态机 — 录制状态、步骤、草稿与发布动作）
- `next-intl` — `skills.desktopRecording` 命名空间文案
- 父模块 [`../_ARCH.md`](../_ARCH.md)
