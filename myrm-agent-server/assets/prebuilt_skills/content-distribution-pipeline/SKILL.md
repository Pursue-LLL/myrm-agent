---
name: content-distribution-pipeline
description: >-
  Content distribution pipeline: adapt a single piece of content for multiple
  platforms in parallel, then run a unified publishing checklist. Uses repeat_for
  to create one adaptation task per selected target platform.
version: 1.1.0
category: pipeline
tags:
  - pipeline
  - content
  - distribution
  - fan-out
  - multi-agent
  - social-media
  - multi-platform
allowed-tools: file_read_tool file_write_tool web_search_tool bash_code_execute_tool
pipeline_spec:
  discovery_questions:
    - group: "source"
      group_label: "Source Content"
      questions:
        - id: "source_content"
          type: "textarea"
          label: "Original content (paste text or provide a file path / URL)"
        - id: "content_type"
          type: "select"
          label: "Content type"
          options: ["Blog Post", "Product Announcement", "Newsletter", "Case Study", "Tutorial", "Opinion / Thought Leadership"]
    - group: "targets"
      group_label: "Target Platforms"
      questions:
        - id: "platforms"
          type: "multi-select"
          label: "Target platforms"
          options:
            - "Twitter / X"
            - "LinkedIn"
            - "WeChat (微信公众号)"
            - "Xiaohongshu (小红书)"
            - "Douyin (抖音短视频)"
            - "Channels (微信视频号)"
            - "Medium / Blog"
            - "Email Newsletter"
            - "Reddit"
            - "YouTube Script"
        - id: "tone"
          type: "select"
          label: "Tone"
          options: ["Professional", "Casual / Conversational", "Technical", "Inspirational"]
  role_templates:
    - role_id: "adapter"
      description: "Adapts source content for a specific platform's format, tone, audience, and algorithm preferences, incorporating personal voice profiles when active"
      required_skills: ["creative-ideation", "content-humanizer", "persona-voice"]
    - role_id: "checker"
      description: "Reviews all adapted versions for consistency, brand voice, visual specs, and publishing readiness"
      required_skills: ["code-review"]
  task_graph_seed:
    - title_template: "Adapt for {_item}"
      description_template: >-
        Adapt the {content_type} for {_item}. Follow the platform-specific SOP in
        assets/prebuilt_skills/content-distribution-pipeline/references/:
        - For Xiaohongshu (小红书): produce Dual Editions (Pain-point decision edition & Experience review edition), a 5-type high-CTR title pool (`xiaohongshu/titles.json`), and 3:4 cover image specs (see references/xiaohongshu-guide.md).
        - For Douyin (抖音短视频): produce a 15-30s short video script with Golden 3-second Hooks, B-roll/visual directions, and 9:16 vertical cover prompt (see references/douyin-guide.md).
        - For WeChat (微信公众号): produce structured in-depth article Markdown plus styled `.wechat.html` artifact via wechat-article-formatter, with 2.35:1 top cover specs (see references/wechat-guide.md).
        - For Channels (微信视频号): produce cognition/business logic focused script tailored for high-net-worth audience (see references/video-account-guide.md).
        - For other platforms: match native character limits, hashtag structures, and {tone} tone.
        Strictly adhere to references/visual-spec.md for all multi-ratio visual deliverables.
      role: "adapter"
      parents: []
      repeat_for: "platforms"
      repeat_for_item_skills:
        "WeChat (微信公众号)":
          - "wechat-article-formatter"
    - title_template: "Publishing Checklist & Consistency Review"
      description_template: >-
        Review all adapted versions for brand consistency, factual accuracy against source,
        and platform-specific compliance. Compile a unified Deliverable Bundle manifest with
        ready-to-publish checklist and visual asset prompts.
      role: "checker"
      parents: [0]
contract:
  steps:
    - "Phase 1 (parallel): Adapt content for each selected platform using platform-specific SOP guides"
    - "Phase 2 (sequential): Cross-platform consistency review, factual auditing, and Deliverable Bundle compilation"
  success_criteria: "Platform-optimized content variants with native algorithm compliance, title pools, video scripts, and visual asset specs"
  estimated_duration_seconds: 3600
---

# Content Distribution Pipeline

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

One-to-many professional content distribution suite: write once, distribute everywhere with native platform depth.

## Core Capabilities & Platform Deep Adapters

1. **Xiaohongshu (小红书)**:
   - **Dual-edition generation**: Version A (Pain-point decision / Avoid pitfalls) vs Version B (Experience review / Grass planting).
   - **High-CTR Title Pool**: 5 formulaic candidate titles (Contrast, Numerical, Warning, Question, Emotion).
   - **Visual Specs**: Standard 3:4 aspect ratio cover layout and card designs.
2. **Douyin / Short Video (抖音短视频)**:
   - **Golden 3-Second Hook**: High-retention opening hooks with action cues.
   - **Shot-by-shot Script**: 15-30s pacing table with spoken lines, visual action, and B-roll guidance.
   - **Visual Specs**: 9:16 vertical full-screen framing prompt.
3. **WeChat Official Account (微信公众号)**:
   - **In-depth Architecture & Narrative**: Deep dive into principles, trade-offs, and boundary analysis.
   - **Rich HTML Artifact**: Automated inline styling generation via `wechat-article-formatter` (`.wechat.html`).
   - **Visual Specs**: 2.35:1 primary banner and 1:1 secondary thumbnail.
4. **Channels (微信视频号)**:
   - **Cognitive & Commercial Framing**: Tailored for business decision-makers and professionals.
5. **Unified Deliverable Bundle**:
   - Cross-platform factual audit, consistency review, and ready-to-publish checklist.

## Reference Guides

- `references/xiaohongshu-guide.md` — Xiaohongshu dual-edition & title pool SOP
- `references/douyin-guide.md` — Douyin golden 3-second hook & short video script SOP
- `references/wechat-guide.md` — WeChat official account long-form narrative & HTML formatting SOP
- `references/video-account-guide.md` — WeChat Channels cognition & business logic SOP
- `references/visual-spec.md` — Multi-platform aspect ratio & cover design specifications
