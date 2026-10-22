# api/instance_archive/

## 架构概述

整实例备份与恢复的 HTTP 薄层（`/api/v1/instance-archive/*`）。业务策略在 [`app/services/instance_archive/`](../../services/instance_archive/_ARCH.md)；本层只做鉴权边界、分块与线程调度、错误码映射。

- 重活不阻塞事件循环：导出跑工作线程（前端轮询进度），分块写入/校验/stage 走 `to_thread`。
- 大文件上传按固定块 PUT（`application/octet-stream`），请求体不超过反向代理/服务端限制；中断后用 `GET /imports/{id}` 的 `received` 续传。
- **配对 token 默认拒绝**：这些路径不在移动端白名单，只有 owner 身份可达。
- 对外只暴露稳定 `code`（如 `export_busy`、`wrong_passphrase`、`newer_schema`），不带服务端措辞；文案在前端 locale。
- 换入结果通过一次性 `GET /outcome`（外壳为 `{outcome: ...|null}`）送达，用户确认后 `POST /outcome/acknowledge` 清除；`POST /rollback` 排队撤销。
- 定时备份挂在 `/auto-backup`：读取与保存设置、立即备份；云端沙箱与非标准布局下 `GET` 返回 `supported=false`，写入类请求返回 `409 unsupported_layout`。端点为 `async def`，使后台线程的告警能交回事件循环。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 包入口 | 路由包标识 | ✅ |
| `router.py` | 核心 | 状态、导出任务（创建/轮询/下载/丢弃）、分块导入（创建/分块/查询/stage/confirm/取消）、一次性 outcome、回滚 | ✅ |
| `auto_backup.py` | 核心 | 定时整实例备份：`GET /auto-backup`（设置 + 最近结果 + 已存副本）、`PUT /auto-backup`（保存设置，参数错误映射为稳定码）、`POST /auto-backup/run`（立即备份，导出进行中返回 `export_busy`） | ✅ |
| `schemas.py` | 核心 | 请求/响应模型（含 `OutcomeEnvelope`、定时备份设置与视图） | ✅ |
