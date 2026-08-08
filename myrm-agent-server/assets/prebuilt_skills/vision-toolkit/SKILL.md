---
name: vision-toolkit
description: >-
  Sandbox image analysis for compare, OCR, region reads, semantic grounding, and
  pixel-level diff. Prefer file_read_tool for a single routine image read.
version: 1.0.0
category: knowledge
tags:
  - vision
  - ocr
  - compare
  - ui
allowed-tools: vision_semantic_tool vision_geometry_tool file_read_tool bash_code_execute_tool desktop_vision_tool browser_snapshot_tool browser_interact_tool
contract:
  steps:
    - "Single undifferentiated image read → file_read_tool first"
    - "Before/after or multi-image judgment → vision_semantic_tool mode=together"
    - "Find a button/field bbox → vision_semantic_tool mode=ground, then desktop_vision_tool or browser_interact_tool"
    - "Exact pixel diff → vision_geometry_tool mode=pixel_diff, then optional region read"
  success_criteria: "Vision conclusions cite tool backend tags and avoid guessing unseen pixels"
---

# vision-toolkit

Use semantic tools for sandbox images under `/workspace`. Do not call provider APIs directly.

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first. Use bash only for ffmpeg frame extraction or pixel scripts when geometry tools are insufficient.

| Question | Tool |
|---|---|
| Read one image generally | `file_read_tool` |
| Compare 2+ images in one judgment | `vision_semantic_tool` mode=`together` |
| Find where X is (bbox) | `vision_semantic_tool` mode=`ground` |
| Read small text in a crop | `vision_semantic_tool` mode=`region` |
| Verbatim OCR | `vision_semantic_tool` mode=`ocr` |
| Pixel-level diff box | `vision_geometry_tool` mode=`pixel_diff` |

Web pages: prefer `browser_snapshot_tool` + `browser_interact_tool` before desktop vision.

Restore workflows:
- Quick UI/layout understanding → stay in together/region reads
- Pixel-level rebuild loops → `pixel_diff` then region reads; avoid endless full-image re-describes
