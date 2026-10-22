# api/machines/ 模块架构

## 架构概述

自托管机群管理与远程实时接管 HTTP 接口层。提供机群列表查询、实时遥测心跳上报、平台专属一键安装注册命令生成，以及人机同屏接管（Seize Takeover / Release to Agent）状态机流转控制端点。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由 | 机群 CRUD、遥测心跳、注册 Token 与接管控制端点 | ✅ |
| `__init__.py` | 入口 | 导出 `router` 门面供主 API 挂载 | ✅ |

## 端点设计

- `GET /api/v1/machines`：机群列表与多维实时指标（CPU/内存/磁盘/活跃任务）
- `GET /api/v1/machines/{id}`：单机节点详情
- `POST /api/v1/machines/token`：生成一键接入 Shell/PowerShell 命令
- `POST /api/v1/machines/{id}/heartbeat`：上报遥测数据
- `POST /api/v1/machines/{id}/takeover`：抢占接管远端屏幕
- `POST /api/v1/machines/{id}/release`：交还控制权给自主 Agent
- `GET /api/v1/machines/{id}/takeover`：获取当前接管会话状态
