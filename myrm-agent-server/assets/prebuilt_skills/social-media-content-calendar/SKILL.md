---
name: social-media-content-calendar
description: >-
  Multi-platform social media content planning, editorial calendar management,
  and cross-channel publishing pipeline. Supports scheduling matrix (X/Twitter,
  Xiaohongshu, WeChat, LinkedIn, Douyin), audience engagement windows, and status tracking.
version: 1.0.0
category: social-media
tags:
  - social-media
  - content-calendar
  - editorial-plan
  - scheduling
  - multi-platform
  - marketing
allowed-tools: file_read_tool file_write_tool file_edit_tool web_search_tool
contract:
  steps:
    - "Phase 1: Goal & Audience Definition — identify core campaign themes, target audience personas, and primary conversion objectives"
    - "Phase 2: Cadence & Matrix Mapping — map content pillars across target channels (X, Xiaohongshu, WeChat, LinkedIn) with optimal posting windows"
    - "Phase 3: Editorial Pipeline Assembly — scaffold monthly/weekly markdown or CSV calendar tables with draft review gates"
    - "Phase 4: Asset & Copy Readiness — ensure platform-specific character limits, media attachments, and CTA links are fully populated"
  potential_traps:
    - description: "Cross-posting identical content across channels without tone/format adaptation"
      mitigation: "Enforce per-platform variation rules: short & provocative on X, visual & tag-heavy on Xiaohongshu, professional on LinkedIn"
      severity: high
    - description: "Scheduling posts outside optimal engagement windows"
      mitigation: "Reference proven audience activity peaks (e.g. 08:30-09:30 morning commute, 12:00-13:00 lunch, 20:00-22:00 evening relaxation)"
      severity: medium
  verification_steps:
    - step_id: calendar_structured
      description: "Calendar is formatted as a structured markdown table or exported CSV with complete dates, channels, topics, and status columns"
      validation_method: "Inspect output table ensuring Date, Channel, Topic, Copy Snippet, Asset Requirement, and Status fields are present"
      is_required: true
  success_criteria: "Clear, multi-platform editorial calendar with complete publishing cadence, channel-specific adaptations, and status review gates"
  estimated_duration_seconds: 400
---

# Social Media Content Calendar (多平台社媒内容排期与营销日历)

A specialized marketing and growth skill for designing, scheduling, and orchestrating comprehensive multi-platform content publishing calendars.

---

## Supported Channels & Formatting Conventions

| Platform | Recommended Post Frequency | Peak Windows (Local Time) | Ideal Format & Key Rules |
|---|---|---|---|
| **X / Twitter** | 2-4 posts / day | 09:00, 12:30, 18:00, 21:30 | Concise hook (< 280 chars), 1 clear idea, 1-2 hashtags max, thread for depth |
| **Xiaohongshu (小红书)** | 1-2 notes / day | 12:00-13:30, 19:30-22:00 | Catchy title (< 20 chars), bullet points, conversational tone, 5-8 relevant tags, 3:4 cover image |
| **WeChat Official (微信公众号)** | 2-3 articles / week | 07:30-08:30, 20:30-22:00 | Deep dive (1500-3000 words), golden 3-second title, clean mobile typography, clear quote blocks |
| **LinkedIn** | 3-5 posts / week | 08:00-10:00, 12:00-14:00 (Tue-Thu) | Professional insights, career lessons, industry analysis, clear whitespace separation |
| **Douyin / Video Channels (视频号)** | 3-5 videos / week | 12:00-13:00, 18:30-21:00 | 15-60s vertical video script, first 3-second retention hook, strong CTA in final 5 seconds |

---

## Standard Editorial Calendar Structure

When generating calendars, output a structured Markdown schedule adhering to the following schema:

```markdown
| Date (YYYY-MM-DD) | Time Slot | Platform | Content Pillar | Topic & Working Title | Key Hook / Copy Snippet | Visual / Asset | Status |
|---|---|---|---|---|---|---|---|
| 2026-09-15 | 09:00 | X / Twitter | Product Launch | Open-source Agent milestone | "Most teams get multi-agent wrong..." | Architecture diagram PNG | Draft |
| 2026-09-15 | 19:30 | Xiaohongshu | Tech Productivity | 个人生活工作台效率看板搭建 | 告别乱糟糟的待办！8个模块搞定每日专注 | 3:4 卡片对比实拍图 | Ready |
| 2026-09-17 | 20:30 | WeChat | Deep Architecture | 深入解析企业级沙箱隔离设计 | 为什么我们重构了整个工具网关？ | 16:9 封面长图 | In Review |
```

---

## Operating Protocol

1. **Clarify Strategy**: Determine the client's current campaign goal (e.g., brand awareness, lead capture, developer adoption).
2. **Determine Frequency & Balance**: Balance 70% value-first educational/entertainment content with 20% engagement/interaction and 10% direct conversion.
3. **Assemble Deliverable**: Write out weekly or monthly calendar schedules to Markdown artifacts or export as CSV for team integration.
