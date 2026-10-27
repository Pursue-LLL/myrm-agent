# project-workspace/

## 架构概述

Project 级同步目录绑定 UI（Mount Wizard）。将用户选择的本地/Tauri 文件夹写入 `Project.workspace_path`，复用已有 Agent bind 管道。

## 文件清单

| 文件                              | 地位 | 职责                                                                                                                                                                    | I/O/P |
| --------------------------------- | ---- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----- |
| `ProjectWorkspaceMount.tsx`       | 核心 | Tauri 原生目录选择 + Web browse 弹层；调用 projects API 持久化绑定；服务端拒绝的目录按原因给出说明；已绑文件夹范围过大而不再被使用时（`workspaceUsable=false`）就地提示 | ✅    |
| `ProjectWorkspaceAdoptDialog.tsx` | 核心 | 外部文件夹一键导入为 Project 弹层；服务端拒绝的目录按原因给出说明                                                                                                       | ✅    |
| `WorkspaceTrustFolderGate.tsx`    | 核心 | 绑定前披露弹层（FolderGate）：披露敏感资产并由用户决定信任或受限运行；决定携带预览时的 `manifest_hash`，被拒绝后重新扫描                                                | ✅    |
| `WorkspaceTrustBanner.tsx`        | 核心 | 顶部常驻通知条：受限文件夹展示被关闭的资产并一键信任；已信任文件夹新增了用户没看过的命令快捷方式时，直接列出并由用户允许                                                | ✅    |

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
