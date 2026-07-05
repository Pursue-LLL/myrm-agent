---
name: bilibili-content
description: >-
  Analyze Bilibili videos by extracting subtitles (CC or AI-generated),
  summarizing content, and identifying key insights. Optimized for Chinese
  video content research, competitive analysis, and knowledge extraction.
version: 1.0.0
category: media
tags:
  - bilibili
  - video
  - subtitle
  - content-analysis
  - media
  - chinese
allowed-tools: web_search_tool web_fetch_tool file_write_tool
contract:
  steps:
    - "Phase 1: Identify — locate the target Bilibili video(s) and extract metadata"
    - "Phase 2: Extract — retrieve subtitle content via fast-path extractor"
    - "Phase 3: Analyze — summarize, extract key points, and identify insights"
    - "Phase 4: Deliver — format findings per user's needs"
  potential_traps:
    - description: "Subtitle unavailable (no CC and no AI subtitle without login)"
      mitigation: "Fall back to video description and title analysis. Inform user they can add Bilibili cookies via SessionVault for AI subtitle access."
      severity: medium
    - description: "AI-generated subtitles may contain recognition errors"
      mitigation: "Cross-reference key terms; flag uncertain passages from context"
      severity: low
    - description: "Some videos are region-locked or require VIP"
      mitigation: "Inform user of access limitation; extract available metadata"
      severity: low
  success_criteria: "Accurate summary with key takeaways and timestamps for important sections"
  estimated_duration_seconds: 600
---

# Bilibili Content Analysis

## Overview

Bilibili (B站) is China's leading video platform with extensive knowledge, educational, and tech content. This skill extracts and analyzes video content without watching — turning hours of Chinese video into structured, actionable notes.

## Phase 1: Identify Videos

### Finding Videos

Use `web_search_tool` with Bilibili-specific queries:
- `site:bilibili.com "topic"` — direct Bilibili results
- `"topic" bilibili 教程` — filtered by type
- BV number lookup: `BV1xx411c7xx` format

### Extract Video Metadata

From a Bilibili URL, the system automatically extracts:
- **BV ID** — the unique video identifier (BV + 10 characters)
- **Title** and **Author (UP主)**
- **Duration**
- **Subtitle availability** (CC / AI-generated / none)

## Phase 2: Extract Content

### Subtitle Extraction

Use `web_fetch_tool` with the Bilibili video URL:

1. **Primary:** The framework's built-in Bilibili extractor automatically retrieves subtitles via API fast-path
2. **With SessionVault cookies:** AI-generated subtitles become accessible (most videos)
3. **Fallback:** Browser-based page crawl returns title, description, and comments

### When Subtitle is Unavailable

Fall back to:
1. Video description (UP主常在描述中放内容大纲)
2. Pinned comments or 置顶评论
3. Related articles on the same topic
4. Danmaku (弹幕) high-frequency keywords as topic indicators

## Phase 3: Analyze

### Summary Levels

Provide the appropriate depth based on user needs:

**Quick Summary (1-2 paragraphs)**
- Main thesis and conclusion
- 3-5 key takeaways

**Detailed Notes**
- Section-by-section breakdown with timestamps
- Key quotes and data points
- Tools, resources, or references mentioned

**Competitive Analysis**
- Compare claims across multiple videos on the same topic
- Identify consensus vs. controversial takes
- Note what each UP主 emphasizes or omits

### Analysis Template

```
## 视频分析: [Title]
UP主: [Name] | 时长: [HH:MM:SS] | BV号: [BVID]

### 摘要
[2-3 sentence overview]

### 关键要点
1. [Timestamp] — [Point]
2. [Timestamp] — [Point]
...

### 重要引述
- "[Direct quote]" — [Context]

### 提到的资源
- [Tool/link/book mentioned in the video]

### 批判性评估
- 优点: [What the video gets right]
- 不足: [What it misses or oversimplifies]
- 倾向: [Any commercial or ideological slant]
```

## Phase 4: Deliver

Format output based on use case:

| Use Case | Format |
|----------|--------|
| Quick reference | Bullet-point summary |
| Study notes | Detailed notes with timestamps |
| Content creation | Key insights + quotable moments |
| Research | Comparative analysis across videos |
| Learning path | Structured knowledge extraction |

### Multi-Video Analysis

When analyzing several videos on the same topic:
1. Create a comparison matrix
2. Identify points of agreement and disagreement
3. Rank videos by depth, accuracy, and production quality
4. Recommend the best starting point for the user
