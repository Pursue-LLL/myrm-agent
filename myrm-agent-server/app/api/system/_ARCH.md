# api/system/

## 架构概述

系统信息、版本、存储优化与受控关机 HTTP 层。上级文档：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `__init__.py` | 入口 | 包入口与导出 | — |
| `router.py` | 路由 | Ingress 需求/URL、LAN 网络信息、存储磁盘信息与会话数据库智能优化（预检/FTS optimize/VACUUM/WAL truncate）、按类别的存储占用台账（`/storage/governance`，只读，类别名由前端本地化）、支持排障包、恢复点（`/storage/snapshots*`，恢复需重启后生效）、OpenTelemetry 导出实测态势（`GET /telemetry-posture`：状态、脱敏端点、协议、采样器、内容外发开关、指标管线 `metrics_status`（`off`/`ready`/`active`/`failing`，按最近一次投递实测）、已导出 Span、失败批次与被隐私守卫拦截的 Span 计数与最近成功/失败时间，全部取自运行中的导出管线，没有写死的能力标志；读取失败时返回 `status=error`；沙箱托管实例（`DEPLOY_MODE=sandbox`）返回 `managed=true` 且不披露采集端地址，因为采集端归平台运营者、用户无需也无法配置） | ✅ |
| `sandbox_recreate.py` | 路由 | 沙箱「重置环境」(`POST /sandbox/recreate`，仅 SaaS 沙箱模式；由 `router.py` 挂载)：代请求控制平面换新容器（持久卷上的工作区文件、聊天、记忆、设置保留）；请求体 `reset_python_env=true`（默认关闭，备份恢复后的「立即重启」不带）时额外在下次启动清除智能体安装的 Python 包：调用控制平面前写重置标记，除控制平面返回 202 外的任何结局（拒绝、不可达、请求被取消而结果未知）都撤回本次请求自己写下的标记（换容器期间旧容器仍在服务，重复点击被控制平面以「正在重建」拒绝时，不会撤掉首次点击留下的标记），由 `services/infra/python_env_reset` 在新容器启动时消费；控制平面只给旧容器 10 秒停止窗口，因此存在运行中的后台 shell 任务或任一 Agent 运行（对话轮次 / cron / IM 渠道 / 看板 / 评测 / 子 Agent，读 `AgentGateway` 与 `run_activity`）时直接 409 拒绝，不发起控制平面请求 | ✅ |
| `schemas.py` | 数据结构 | System API 请求、响应与存储治理数据传输模型 (Pydantic) | ✅ |
| `model_ping_api.py` | 路由 | 模型配置一键测速与连通性自检 (`POST /system/model-ping`)，返回首字延迟 TTFT、吞吐量 TPS 与鉴权可用性徽标 | ✅ |
| `shutdown.py` | 模块 | HTTP shutdown/drain control — `POST /shutdown` (graceful SIGTERM), `POST /drain` (begin draining), `DELETE /drain` (cancel drain). | ✅ |



