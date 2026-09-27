# project-workspace/

## 架构概述

Project 级同步目录绑定 UI（Mount Wizard）。将用户选择的本地/Tauri 文件夹写入 `Project.workspace_path`，复用已有 Agent bind 管道。

## 文件清单

| 文件                              | 地位 | 职责                                                                 | I/O/P |
| --------------------------------- | ---- | -------------------------------------------------------------------- | ----- |
| `ProjectWorkspaceMount.tsx`       | 核心 | Tauri 原生目录选择 + Web browse 弹层；调用 projects API 持久化绑定   | ✅    |
| `ProjectWorkspaceAdoptDialog.tsx` | 核心 | 外部文件夹一键导入为 Project 弹层                                    | ✅    |
| `WorkspaceTrustFolderGate.tsx`    | 核心 | 绑定前披露弹层（FolderGate）：披露敏感资产并由用户决定信任或受限运行 | ✅    |
| `WorkspaceTrustBanner.tsx`        | 核心 | 受限模式顶部常驻通知条：展示隔离资产统计与一键信任解除隔离           | ✅    |

## 依赖

- `@/services/projects`、`@/services/chat`（browseDirectories）、`@/services/workspaceTrust`
- `@tauri-apps/plugin-dialog`（桌面端）
- 父模块 [`features/_ARCH.md`](../_ARCH.md)

## 关联

- Server：`myrm-agent-server/app/services/project/workspace_path_resolve.py`
- Server 信任接口：`myrm-agent-server/app/api/security/workspace_trust.py`
- 侧栏入口：[`sidebar/ProjectBar.tsx`](../sidebar/ProjectBar.tsx)
- 聊天主窗口：[`chat-window/ChatWindow.tsx`](../chat-window/ChatWindow.tsx)
- Onboarding：[`onboarding/SyncFolderOnboardingStep.tsx`](../onboarding/SyncFolderOnboardingStep.tsx)
