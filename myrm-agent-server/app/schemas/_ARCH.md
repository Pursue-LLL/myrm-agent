# app/schemas 模块架构

共享 Pydantic DTO 层。API 与 services 均从此导入，禁止 services 反向依赖 app.api。

## 文件清单

| 文件 | 职责 |
|------|------|
| `streaming.py` | SSE envelope 与标准响应头（`Cache-Control: no-cache, no-transform`：转发 `/api/v1` 的 Next.js 服务器会 gzip 它能压的响应，安静的 attach 流会被缓冲到空闲超时才出数据，`no-transform` 让它不压） |
| `config.py` | 配置同步 API 模型（含 `personalSettings.reasoningDisplayMode`：off/collapsed/inline、`personalSettings.autoContinueInterruptedTurns`：崩溃自动续跑开关、`personalSettings.themeProfiles` Theme Recipe 校验） |
| `theme_profile.py` | Theme Engine Recipe Pydantic 模型（`file:` assetRef、`themeProfiles` 校验） |
| `control_plane.py` | Server↔CP 遥测契约（含 context compaction、memory brief `envelope_id(max_length=128)` + `aggregates`/`dropped_aggregates`、memory guardian guard `envelope_id(max_length=128)` + governed `reason/guard/frequency_tier` 聚合） |
| `memory/command_center.py` | Memory Command Center 响应模型 |
| `responses.py` | 标准化 API 响应信封模型（`StandardSuccessResponse`/`StandardErrorResponse`）、业务码枚举 `BusinessCode`、工厂函数 `create_success_response`/`create_list_response`/`create_error_response`。错误信封的 `error.trace_id` 默认取当前请求的 trace id（`resolve_current_trace_id`：OpenTelemetry 优先，其次 TracingContext，请求之外才新生成）；带 `details`、显式 `trace_id` 或业务码 ≥ 50000（服务端故障）时才返回 `error` 块，普通 4xx 仍只有 message |
| `security/dashboard.py` | 安全仪表盘 DTO（API + services 共用） |
| `desktop_recorder.py` | 桌面工作流录制请求/响应 DTO（`Start/Stop/Synthesize/Analyze/Compile/Publish` 契约 + `WorkflowIntentPlanSchema`）。运行时会话状态归 services 层，故本 DTO 层不依赖 services |








