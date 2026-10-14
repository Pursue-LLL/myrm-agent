# workspace-boundary 模块

## 架构概述

提供工作区多维执行边界 HUD 状态栏、三当前状态核验与低风险项目切换握手协议 UI（Roadmap ⑨ Item 58 P0）。彻底杜绝命令在错误环境执行成功或跨会话串线的认知错位。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `workspaceBoundaryTypes.ts` | 核心类型 | 定义三当前执行边界、握手协议请求/响应与 Worktree 实体模型 | ✅ |
| `workspaceBoundaryService.ts` | 客户端服务 | 封装与后端 `/api/v1/workspace/boundary/*` 的通信与离线降级 | ✅ |
| `WorkspaceBoundaryHud.tsx` | 核心 UI | 顶部常驻高显三当前胶囊状态条（目标、Git 分支/脏状态、执行宿主） | ✅ |
| `BoundaryHandshakeCard.tsx` | 交互卡片 | 跨项目切换时微型只读环境探针握手卡片与风险核验拦截 | ✅ |
| `WorktreeMatrixNavigator.tsx` | 导航面板 | 多仓库与 Git Worktree 矩阵式导航面板 | ✅ |
| `index.ts` | 门面导出 | 导出类型、服务与各核心组件 | ✅ |

## 依赖关系

### 外部依赖
- `lucide-react` — 矢量图标呈现（Target, GitBranch, Laptop, Cloud, ShieldCheck 等）

### 内部依赖
- `locales/{lang}.json` 的 `workspaceBoundary` 命名空间 — 六语国际化文案
