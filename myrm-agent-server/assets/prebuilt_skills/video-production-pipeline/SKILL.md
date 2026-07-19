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
