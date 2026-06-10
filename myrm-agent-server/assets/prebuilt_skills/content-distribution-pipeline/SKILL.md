---
name: content-distribution-pipeline
description: >-
  Content distribution pipeline: adapt a single piece of content for multiple
  platforms in parallel, then run a unified publishing checklist. Uses repeat_for
  to create one adaptation task per selected target platform.
version: 1.0.0
category: pipeline
tags:
  - pipeline
  - content
  - distribution
  - fan-out
  - multi-agent
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
      description: "Adapts source content for a specific platform's format, tone, and audience"
      required_skills: ["creative-ideation", "content-humanizer"]
    - role_id: "checker"
      description: "Reviews all adapted versions for consistency, brand voice, and publishing readiness"
      required_skills: ["code-review"]
  task_graph_seed:
    - title_template: "Adapt for {_item}"
      description_template: >-
        Adapt the {content_type} for {_item}. Match the platform's native
        format (character limits, hashtags, visual layout, etc.) and apply
        a {tone} tone. Preserve the core message while optimizing for
        engagement on {_item}.
      role: "adapter"
      parents: []
      repeat_for: "platforms"
    - title_template: "Publishing Checklist & Consistency Review"
      description_template: >-
        Review all adapted versions for brand consistency, factual accuracy,
        and platform-specific compliance. Produce a ready-to-publish
        checklist with any final edits.
      role: "checker"
      parents: [0]
contract:
  steps:
    - "Phase 1 (parallel): Adapt content for each selected platform"
    - "Phase 2 (sequential): Cross-platform consistency review and publishing checklist"
  success_criteria: "Platform-optimized content variants with consistent messaging"
  estimated_duration_seconds: 3600
---

# Content Distribution Pipeline

One-to-many content adaptation: write once, distribute everywhere.

## How It Works

1. **Paste your content** — a blog post, announcement, newsletter, etc.
2. **Select target platforms** — each platform gets a dedicated adaptation task running in parallel
3. **Consistency review** — after all adaptations complete, a reviewer ensures brand consistency across all versions
