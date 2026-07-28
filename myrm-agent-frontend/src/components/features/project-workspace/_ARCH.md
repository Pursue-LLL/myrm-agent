# project-workspace/

## 架构概述

Project 级同步目录绑定 UI（Mount Wizard）。将用户选择的本地/Tauri 文件夹写入 `Project.workspace_path`，复用已有 Agent bind 管道。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `ProjectWorkspaceMount.tsx` | 核心 | Tauri 原生目录选择 + Web browse 弹层；调用 projects API 持久化绑定 | ✅ |

## 依赖

- `@/services/projects`、`@/services/chat`（browseDirectories）
- `@tauri-apps/plugin-dialog`（桌面端）
- 父模块 [`features/_ARCH.md`](../_ARCH.md)

## 关联

- Server：`myrm-agent-server/app/services/project/workspace_path_resolve.py`
- 侧栏入口：[`sidebar/ProjectBar.tsx`](../sidebar/ProjectBar.tsx)
- Onboarding：[`onboarding/SyncFolderOnboardingStep.tsx`](../onboarding/SyncFolderOnboardingStep.tsx)
