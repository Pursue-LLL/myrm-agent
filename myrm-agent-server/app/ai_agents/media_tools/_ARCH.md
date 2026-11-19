# media_tools/

## Overview

Product-layer LangChain adapters for image/video/TTS generation. Engines live in
`myrm-agent-harness/toolkits/llms/{image,video,tts}/`. Every generated artifact is stored in the media library
before a tool or task reports success and is addressed everywhere as `media://<id>`; a failure to store it is a failed
generation, never a result without a file.

## Files

| File | Role |
|------|------|
| `__init__.py` | 包级统一出口门面（SSOT Facade），导出 `clamp_image_payload`、`create_image_generation_tool`、`create_video_generation_tool`、`create_tts_tool`、`create_media_persist_callback` |
| `image_clamp.py` | `clamp_image_payload` 纯函数（防 413 Payload 超限、EXIF 拍摄角度物理纠偏、RGBA 透明底板 Alpha 混合合成纯净 RGB、坏图优雅降级与小图无损直通），作为输入解析器的图片处理钩子 |
| `input_policy.py` | `build_media_input_policy`：工具与任务执行器共用的引用解析策略 —— `media://` 加载器、工作区允许根目录、图片钩子；`allowed_roots` 随任务载荷快照，执行器据此解析 |
| `task_results.py` | 三个工具共用的结果形状：`tool_error`、`media_task_store`（调用时取任务库）、`started_tasks_result`（`tasks[{task_id,task_type,status}]`）、`media_task_status_result`（`status` 动作；失败任务带 `next_step`） |
| `image_agent_tool.py` | `create_image_generation_tool` → `image_tool`：`generate` 每张图一个后台任务（`n` 个任务，不把 `n` 传给供应商）并返回任务列表；`edit` 单图同步返回，要求可编辑的模型，`n>1` 明确报错；`status` / `list`；参数只用官方取值（`quality` 为 low/medium/high 可选，无 `style`）；`quality` 只随 OpenAI 兼容线路（`openai_chat`、`azure_openai`）的生成与改图请求下发，Gemini、Stability、MiniMax 的请求不带它；属于另一个动作的参数（`generate` 带 `image_url` / `mask_url` / `task_id`，`edit` 带 `reference_image_urls` / `task_id`；空串与空列表等于没传）明确报错而不是被丢弃；引用文件由 worker 经统一解析器解析，坏引用让任务失败并指出字段名 |
| `media_persist.py` | 三个引擎共用的落库回调：无论有无会话都落库（后台任务没有 `chat_id`），返回 `media://<id>`，落库失败抛错使生成失败 |
| `video_agent_tool.py` | `create_video_generation_tool` → `video_tool`：`generate` 入队一个后台任务并返回任务列表，参考图 / 参考视频由 worker 解析；`status` 查统一任务状态；`list` 列出供应商与模型 |
| `video_schema.py` | `build_video_input_schema`：按活跃 Provider Capabilities 动态裁剪不支持的参数，`ConfigDict(extra="allow")` 超集透传，每个供应商的 schema 固定以保护 Prompt Cache |
| `tts_agent_tool.py` | `create_tts_tool` → `tts_generate`：文本转语音，可选 `style`（仅火山 Seed-Audio 生效），空文本与 1500 字符上限防护，结果带 `audio_url`（`media://`）、`model`、`duration_seconds`，只有音频已落库才报成功 |

## Mount policy

A tool is mounted only when the user has chosen what it runs: an image model in the catalog, a video provider that
serves the chosen model, or a TTS provider/model/voice that the engine supports. Credentials alone mount nothing and no
default is substituted (see `app/core/media/selection.py`). Mounted tools are **AgentDeclared** (eager, Turn 1 schema)
via `general_agent/tool_setup/` — not deferred. The schema text is fixed per configuration, and dynamic guidance
(`next_step`) appears only in `status` results, so the stable prompt prefix does not change between turns.

## Result registration

The stream collector registers the media of each tool call from the tool's structured result
(`app/services/agent/streaming_support/media_generated.py`), so a card never depends on what the model writes.
