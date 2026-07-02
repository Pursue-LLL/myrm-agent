# media_tools/

## Overview

Product-layer LangChain adapters for image/video/TTS generation. Engines live in
`myrm-agent-harness/toolkits/llms/{image,video,tts}/`.

## Files

| File | Role |
|------|------|
| `media_constants.py` | `PRODUCT_MEDIA_TOOL_NAMES` SSOT |
| `image_agent_tool.py` | `create_image_generation_tool` → `image_tool` |
| `video_agent_tool.py` | `create_video_generation_tool` → `video_tool` |
| `tts_agent_tool.py` | `create_tts_tool` → `tts_generate` |

## Mount policy

When the user enables `image_generation` / `video_generation` / `tts` on an agent
and credentials are configured, tools are registered as **AgentDeclared** (eager,
Turn 1 schema) via `general_agent/tool_setup.py` — not deferred.
