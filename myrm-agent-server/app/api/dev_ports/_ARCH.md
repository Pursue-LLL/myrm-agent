# Dev Ports API Module

## 架构定位

本模块为开发服务器活跃端口嗅探、进程管理与即时预览中枢（DevPortsListeningBarAndServicePreviewHub）的后端服务接口层。负责管理沙箱或本地运行的 Web/API 服务（如 Vite、Next.js、FastAPI 等），提供活跃端口列表查询、端口注册感知、服务进程关闭与临时内网穿透/外网共享预览隧道 URL 生成。

## 模块清单

| 文件 | 职责 | 规范要求 |
|---|---|---|
| `routes.py` | 暴露 `GET /api/v1/dev-ports`、`POST /api/v1/dev-ports`、`DELETE /api/v1/dev-ports/{port}`、`POST /api/v1/dev-ports/{port}/tunnel` | `< 150` 行，强类型 Pydantic 模型，无 `Any` |
| `__init__.py` | 统一导出门面路由 | 标准包导出 |
| `_ARCH.md` | 本目录架构与文件索引 | 遵循架构规范 |

## 核心接口说明

- `GET /api/v1/dev-ports`：获取当前所有正在监听的开发端口、进程名称与服务 URL；
- `POST /api/v1/dev-ports`：注册新嗅探到的开发服务端口；
- `DELETE /api/v1/dev-ports/{port}`：安全关闭指定端口的开发进程；
- `POST /api/v1/dev-ports/{port}/tunnel`：为指定端口生成临时共享隧道链接。
