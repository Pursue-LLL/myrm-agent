---
name: video-production-pipeline
description: >-
  End-to-end video production pipeline: research, scripting, visual design,
  production, and review. Creates a multi-agent Kanban task graph with parallel
  execution for efficient video delivery.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - video
  - production
  - multi-agent
  - creative
allowed-tools: file_read_tool file_write_tool web_search_tool bash_code_execute_tool video_tool image_tool tts_generate
pipeline_spec:
  discovery_questions:
    - group: "basic_info"
      group_label: "基础信息"
      questions:
        - id: "video_type"
          type: "select"
          label: "视频类型"
          options: ["产品宣传", "教程/教学", "叙事短片", "音乐MV", "品牌故事", "活动回顾"]
        - id: "duration"
          type: "select"
          label: "目标时长"
          options: ["15-30s (短视频)", "30-90s (社交媒体)", "1-3min (YouTube)", "3-10min (深度内容)"]
        - id: "platform"
          type: "select"
          label: "发布平台"
          options: ["抖音/TikTok", "小红书", "YouTube", "B站", "微信视频号", "通用"]
    - group: "content"
      group_label: "内容细节"
      questions:
        - id: "topic"
          type: "text"
          label: "视频主题/产品名称"
        - id: "style"
          type: "select"
          label: "视觉风格"
          options: ["简约现代", "活泼多彩", "电影质感", "科技未来", "复古怀旧", "自然清新"]
  role_templates:
    - role_id: "researcher"
      description: "负责市场调研、竞品分析和素材收集"
      required_skills: ["deep-research", "web-scraping"]
    - role_id: "writer"
      description: "负责脚本撰写、文案策划和节奏设计"
      required_skills: ["creative-ideation"]
    - role_id: "designer"
      description: "负责视觉风格设计、分镜设计和动效规划"
      required_skills: ["creative-ideation"]
    - role_id: "creator"
      description: "负责视频素材制作、剪辑和后期合成"
      required_skills: ["creative-ideation"]
    - role_id: "reviewer"
      description: "负责质量审核、平台合规检查和最终交付"
      required_skills: ["code-review"]
  task_graph_seed:
    - title_template: "调研：{video_type}领域素材与竞品"
      description_template: "收集 {platform} 平台上 {video_type} 类型的优秀案例，分析{topic}相关的市场趋势和用户偏好"
      role: "researcher"
      parents: []
    - title_template: "设计视觉风格：{style}"
      description_template: "基于{style}风格为{topic}设计视觉语言，包括色彩方案、排版风格和动效参考"
      role: "designer"
      parents: []
    - title_template: "撰写{duration}脚本"
      description_template: "基于调研结果，为{topic}撰写{duration}的{video_type}脚本，匹配{platform}平台用户习惯"
      role: "writer"
      parents: [0]
    - title_template: "制作视频"
      description_template: "根据脚本和视觉风格方案，制作{duration}的{video_type}视频"
      role: "creator"
      parents: [1, 2]
    - title_template: "审查与交付"
      description_template: "审核视频质量，确认符合{platform}平台规范和{duration}时长要求，准备发布"
      role: "reviewer"
      parents: [3]
contract:
  steps:
    - "Phase 1: Research — collect reference materials and competitor analysis"
    - "Phase 2: Visual Design — define the visual language and style guide"
    - "Phase 3: Script Writing — create the narrative structure and script"
    - "Phase 4: Production — produce the video with all assets"
    - "Phase 5: Review & Delivery — quality check and platform compliance"
  success_criteria: "Delivered video meeting platform specs with consistent visual style and engaging narrative"
  estimated_duration_seconds: 7200
---

# Video Production Pipeline

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

A structured pipeline for creating professional videos, from initial research through final delivery. Leverages multiple specialized agents working in parallel where possible.

## How This Pipeline Works

1. **Research** and **Visual Design** run in parallel — no dependency between them
2. **Script Writing** depends on research completion
3. **Production** depends on both script and visual design being ready
4. **Review** is the final gate before delivery

## Role Responsibilities

| Role | Focus Area | Key Deliverables |
|------|-----------|------------------|
| Researcher | Market analysis, trend spotting | Reference report, competitor examples |
| Designer | Visual language, style guide | Mood board, color palette, motion reference |
| Writer | Narrative structure, pacing | Complete script with timing marks |
| Creator | Asset production, editing | Final video file |
| Reviewer | Quality assurance, compliance | Approval or revision notes |

## Shot Pipeline Best Practices

Video generation providers limit each clip to **6–12 seconds**. Any video longer than a single clip requires a multi-shot pipeline.

### Step 1 — Discover provider capabilities

Before planning shots, call `video_tool(action="list")` and read `max_duration_seconds` and `supported_durations` from the active provider's capabilities. Use these values (not hardcoded numbers) to plan shot duration.

### Step 2 — Plan shots & Cinematic Storyboard Specification

Divide the target duration into shots that fit the provider's supported durations. Prefer the shortest supported duration (typically 5s or 6s) for tighter creative control. Each shot should have a clear purpose: establishing, action, detail, transition, or closing.

To maximize video rendering fidelity across modern neural video engines (FAL Kling, FLUX.3 Video, Sora, MiniMax), structure each scene prompt using the **Cinematic Storyboard JSON specification** before invoking `video_tool`:

```json
{
  "scene_id": "shot_01",
  "composition": {
    "shot_type": "Extreme Close-up / Medium Shot / Wide Establishing",
    "camera_motion": "Slow 120fps Dolly-in / Static handheld / Dynamic Pan Right",
    "angle": "Low angle / Eye level / Dutch angle",
    "focal_depth": "Shallow depth of field, sharp subject focus with soft anamorphic bokeh"
  },
  "visual_elements": {
    "subject": "Detailed character or product action, texture, material physics",
    "environment": "Atmospheric lighting, volumetric fog, rim light, golden hour",
    "motion_dynamics": "High speed fluid splashes, dynamic fabric flutter, particle drift"
  },
  "negative_constraints": "blurry, distorted facial features, text artifacts, watermarks, jittery motion",
  "technical_overrides": {
    "duration_seconds": 5,
    "aspect_ratio": "16:9",
    "resolution": "1080p"
  }
}
```

When passing to `video_tool(action="generate")`, compile the JSON elements into a dense, cinematic prompt string:
`[Shot Type + Angle] + [Subject Action & Texture] + [Lighting & Environment] + [Camera Motion]`.
Example compiled prompt:
> *"Cinematic macro close-up, eye-level framing. Cold brew coffee slowly dripping through crystal glass filter, tiny amber droplets splashing into ice cubes with fluid physics. Dramatic warm rim lighting, dark studio backdrop with volumetric haze. 120fps high-speed slow motion, subtle dolly forward, photorealistic 8k commercial quality."*


### Step 3 — Generate a base image for visual consistency

Before generating video clips, use `image_tool` to create a single **base image** that anchors the visual style (character appearance, color palette, lighting). Reuse this image as `reference_images` for every shot to maintain consistency across clips.

### Step 4 — Generate clips with I2V

For each shot, call `video_tool(action="generate")` with:
- `reference_images` pointing to the base image (or a targeted edit of it for the specific shot)
- `enable_audio=false` to produce silent clips — this prevents per-clip ambient sound from conflicting with the final soundtrack
- `duration_seconds` set to the provider's supported value from Step 1

### Step 5 — Concatenate with FFmpeg

After all clips are generated, use `bash_code_execute_tool` to concatenate them losslessly:

```bash
ffmpeg -f concat -safe 0 -i list.txt -c copy output.mp4
```

Where `list.txt` contains one `file '/path/to/shotN.mp4'` entry per clip in sequence order.

### Step 6 — Add soundtrack

If background music or voiceover is needed, overlay it on the concatenated video:

```bash
ffmpeg -i output.mp4 -i bgm.mp3 -filter_complex "[1:a]afade=t=in:d=1,afade=t=out:st=<END-1>:d=1[a]" -map 0:v -map "[a]" -shortest final.mp4
```

### Step 7 — Verify keyframe quality

Before delivering, spot-check generated clips for artifacts. If the scene is complex (many characters, fine text, intricate backgrounds), verify that keyframes are clean — no watermarks, garbled text, or visual glitches. Use vision tools to inspect extracted frames when in doubt. If a clip fails quality check, regenerate that single shot with a simplified prompt.
