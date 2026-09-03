# media_tools/

## Overview

Product-layer LangChain adapters for image/video/TTS generation. Engines live in
`myrm-agent-harness/toolkits/llms/{image,video,tts}/`.

## Files

| File | Role |
|------|------|
| `__init__.py` | 包级统一出口门面（SSOT Facade），导出 `clamp_image_payload`、`create_image_generation_tool`、`create_video_generation_tool`、`create_tts_tool`、`create_media_persist_callback` |
| `image_clamp.py` | `clamp_image_payload` 纯函数（防 413 Payload 超限、EXIF 拍摄角度物理纠偏、RGBA 透明底板 Alpha 混合合成纯净 RGB、坏图优雅降级与小图无损直通） |
| `image_agent_tool.py` | `create_image_generation_tool` → `image_tool` (generate async via TaskStore + `payload_postprocessor=seal_task_payload_secrets` before persist; status 支持按 task_id 查询统一任务进度与成品 URL；edit/list sync；自动调用 `clamp_image_payload` 守护下载输入图) |
| `media_persist.py` | Shared media library persist callback for sync + async image paths |
| `video_agent_tool.py` | `create_video_generation_tool` → `video_tool`（generate 强制非空 prompt，支持 negative_prompt 与 seed，自动调用 `clamp_image_payload` 守护参考图片输入流，优先 async enqueue 到 TaskStore；status 支持按 task_id 查统一任务状态） |
| `tts_agent_tool.py` | `create_tts_tool` → `tts_generate` |

## Mount policy

When the user enables `image_generation` / `video_generation` / `tts` on an agent
and credentials are configured, tools are registered as **AgentDeclared** (eager,
Turn 1 schema) via `general_agent/tool_setup.py` — not deferred.
