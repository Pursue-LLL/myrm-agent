# projectWorkspace/

## 架构概述

「工作区 - 项目」两级层级与项目内话题分支会话的纯逻辑层：项目容器（根路径、记忆分区、自定义指令、标签）、项目内分支会话（继承策略），以及依据首轮提问推导意图标题并自动重命名会话。单例管理器，无 React 依赖。

## 子模块

| 路径                                        | 职责                                                                                                                                                                                                                 |
| ------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `workspaceProjectManager.ts`                | `WorkspaceProjectManager` 单例：项目（`createProject` / `getProject` / `listProjects` / `updateProjectInstructions`）、分支会话（`createSessionBranch` / `getSession` / `listProjectSessions`）、意图命名（`deriveIntentTitle` / `renameSessionByIntent`）、`clear` / `resetInstance` |
| `projectHierarchyTypes.ts`                  | 数据契约：`ProjectContainer`、`TopicSessionBranch`、`BranchInheritancePolicy`、`IntentNamingResult`                                                                                                                  |
| `index.ts`                                  | 门面：re-export 管理器、`CreateProjectParams` 与层级类型                                                                                                                                                             |
| `__tests__/workspaceProjectManager.test.ts` | 管理器单测                                                                                                                                                                                                           |
