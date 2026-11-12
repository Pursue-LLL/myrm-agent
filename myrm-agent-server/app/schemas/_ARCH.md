# app/schemas 模块架构

共享 Pydantic DTO 层。API 与 services 均从此导入，禁止 services 反向依赖 app.api。

## 文件清单

| 文件 | 职责 |
|------|------|
| `streaming.py` | SSE envelope 与标准响应头（`Cache-Control: no-cache, no-transform`：转发 `/api/v1` 的 Next.js 服务器会 gzip 它能压的响应，安静的 attach 流会被缓冲到空闲超时才出数据，`no-transform` 让它不压） |
| `config.py` | 配置同步 API 模型（含 `personalSettings.reasoningDisplayMode`：off/collapsed/inline、`personalSettings.autoContinueInterruptedTurns`：崩溃自动续跑开关、`personalSettings.themeProfiles` Theme Recipe 校验） |
| `theme_profile.py` | Theme Engine Recipe Pydantic 模型（`file:` assetRef、`themeProfiles` 校验） |
| `control_plane/` | 子包 | Server↔CP 遥测契约，按数据族分 4 个模块（context_events / context_snapshot / coercion / telemetry）：上下文压缩/重取/归档恢复快照、Memory Brief 与 Guardian 遥测信封。见 [control_plane/_ARCH.md](control_plane/_ARCH.md) | ✅ |
| `memory/command_center/` | Memory Command Center 响应模型 |
| `responses.py` | 标准化 API 响应信封模型（`StandardSuccessResponse`/`StandardErrorResponse`）、业务码枚举 `BusinessCode`、工厂函数 `create_success_response`/`create_list_response`/`create_error_response`。错误信封的 `error.trace_id` 默认取当前请求的 trace id（`resolve_current_trace_id`：OpenTelemetry 优先，其次 TracingContext，请求之外才新生成）；带 `details`、显式 `trace_id` 或业务码 ≥ 50000（服务端故障）时才返回 `error` 块，普通 4xx 仍只有 message |
| `security/dashboard.py` | 安全仪表盘 DTO（API + services 共用） |
| `desktop_recorder.py` | 桌面工作流录制请求/响应 DTO（`Start/Stop/Synthesize/Analyze/Compile/Publish` 契约 + `WorkflowIntentPlanSchema`）。运行时会话状态归 services 层，故本 DTO 层不依赖 services |
| `compounding_playbook.py` | 复利剧本（compounding playbook）状态 API 的响应模型 |
| `ephemeral_delta.py` | 临时增量记忆 API 的 DTO：动作词表 `override` / `add_fact` / `revoke`（`revoke` 是墓碑增量在 API 上的名字）、记录请求、会话快照、布局指标与注入预览 |
| `inbound_quarantine.py` | 入站凭据隔离与物理隔离区的服务端 DTO 契约 |
| `onboarding_insight.py` | 外部 Agent 历史接入的 DTO：来源探测、初见报告生成与确认写入记忆 |
| `ops.py` | `GET /api/v1/ops/snapshot` 运维聚合快照的数据契约：一次请求给出控制面、WebUI/桌面端与 CLI 所需的全景可观测数据 |
| `private_notebook.py` | 模型私有笔记本 API 的 DTO：笔记元数据、正文、追加与改写请求、搜索命中，历史上下文与条目，新上下文切换请求与响应 |
| `profile_notes.py` | 用户画像与工作笔记两层记忆的 DTO：写入噪声过滤结果与容量水位指标 |
| `score_honesty.py` | 检索分数诚实度 API 的请求/响应模型：把原始物理相似度与综合排序分数分开 |
| `two_layer_dialectic.py` | 两层上下文注入与多轮辩证调和 API 的 DTO |
| `workflow_templates.py` | 工作流模板库 API 的 DTO：摘要、列表与详情，保存与从运行保存请求，主干准入请求与响应 |
