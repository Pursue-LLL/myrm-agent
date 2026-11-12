# api/machines/ 模块架构

## 架构概述

机群 HTTP 接口层：列出注册表里的机器、返回单台机器、生成接入命令，以及开始、交还和查询某台机器的接管会话。数据来自 `services/machines` 的进程内注册表，该注册表启动时只有两台示例节点；接口不连接真实机器，也不传输屏幕画面。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `router.py` | 路由 | 机群查询、接入命令与接管控制端点 | ✅ |
| `__init__.py` | 入口 | 导出 `router` 门面供主 API 挂载 | ✅ |

## 端点设计

- `GET /api/v1/machines`：注册表中的机器列表，每台机器带一份指标快照（CPU/内存/磁盘/活跃任务）
- `GET /api/v1/machines/{id}`：单机节点详情，机器不存在返回 404
- `POST /api/v1/machines/token`：按 `platform` 查询参数（默认 `darwin`）生成 Shell 或 PowerShell 接入命令，返回 201
- `POST /api/v1/machines/{id}/takeover`：把该机器及其接管会话切到人工接管，机器不存在返回 404
- `POST /api/v1/machines/{id}/release`：交还给自主 Agent，机器不存在返回 404
- `GET /api/v1/machines/{id}/takeover`：返回当前接管会话，没有会话时返回 `null`
