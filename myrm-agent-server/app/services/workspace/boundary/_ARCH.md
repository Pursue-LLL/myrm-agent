# 工作区执行边界与三当前状态核验服务 (boundary)

## 架构概述

提供工作区多维执行边界 HUD 状态探测、Git Worktree 矩阵导航与跨项目切换低风险只读握手协议支持（Roadmap ⑨ Item 58 P0）。彻底杜绝命令在错误环境执行成功或跨会话串线的认知错位。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `boundary_types.py` | 核心契约 | 定义 ThreeCurrentsBoundary、Handshake 请求响应与 Worktree 数据模型 | ✅ |
| `workspace_boundary_service.py` | 核心引擎 | 宿主识别、只读 Git 状态探针与项目切换握手协议校验器 | ✅ |
| `__init__.py` | 门面导出 | 导出核心模型与探测服务类 | ✅ |

## 依赖关系

### 内部依赖
- `platform`, `subprocess`, `os`, `time`, `hmac`, `hashlib` — 平台宿主感知与轻量只读命令执行

### 被依赖方
- `app.api.workspace.workspace_boundary_router` — 暴露 REST API 端点供前端 Header 与 HUD 消费
