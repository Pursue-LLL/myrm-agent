# app/schemas 模块架构

共享 Pydantic DTO 层。API 与 services 均从此导入，禁止 services 反向依赖 app.api。

## 文件清单

| 文件 | 职责 |
|------|------|
| `streaming.py` | SSE envelope 与标准响应头 |
| `config.py` | 配置同步 API 模型 |
| `control_plane.py` | Server↔CP 遥测契约（含 context compaction、memory brief `envelope_id(max_length=128)` + `aggregates`/`dropped_aggregates`、memory guardian guard `envelope_id(max_length=128)` + governed `reason/guard/frequency_tier` 聚合） |
| `memory/command_center.py` | Memory Command Center 响应模型 |
| `security/dashboard.py` | 安全仪表盘 DTO（API + services 共用） |
