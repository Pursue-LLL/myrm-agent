---
name: youtube-content
description: >-
  Analyze YouTube videos by extracting transcripts, summarizing content, and
  identifying key insights. Supports content research, competitive analysis,
  and knowledge extraction from video content.
version: 1.0.0
category: media
tags:
  - youtube
  - video
  - transcript
  - content-analysis
  - media
allowed-tools: web_search_tool web_fetch_tool file_write_tool
contract:
  steps:
    - "Phase 1: Identify — locate the target video(s) and extract metadata"
    - "Phase 2: Extract — retrieve transcript or description content"
    - "Phase 3: Analyze — summarize, extract key points, and identify insights"
    - "Phase 4: Deliver — format findings per user's needs"
  potential_traps:
    - description: "Transcript unavailable for some videos"
      mitigation: "Fall back to description + comments analysis. Inform user of limitation."
      severity: medium
    - description: "Auto-generated transcripts may have errors"
      mitigation: "Cross-reference key terms and numbers; flag uncertain passages"
      severity: low
  success_criteria: "Accurate summary with key takeaways and timestamps for important sections"
  estimated_duration_seconds: 600
---

# YouTube Content Analysis

## Overview

YouTube is the world's second-largest search engine with vast knowledge content. This skill extracts and analyzes video content without watching — turning hours of video into structured, actionable notes.

## Phase 1: Identify Videos

### Finding Videos

Use `web_search_tool` with YouTube-specific queries:
- `site:youtube.com "topic"` — direct YouTube results
- `"topic" youtube tutorial 2024` — filtered by type and recency

### Extract Video Metadata

From a YouTube URL, extract:
- **Video ID** — the 11-character string after `v=`
- **Title** and **Channel name**
- **Duration** and **Upload date**
- **View count** — proxy for content value

## Phase 2: Extract Content

### Transcript Extraction

Use `web_fetch_tool` to access transcript services:

1. **Primary:** Fetch `https://www.youtube.com/watch?v=VIDEO_ID` and look for transcript data
2. **Alternative:** Use third-party transcript APIs if available

### When Transcript is Unavailable

Fall back to:
1. Video description (often contains outlines and timestamps)
2. Pinned comments (creators often post summaries)
3. Related blog posts or articles (search for the video title)
4. Chapter markers (visible in the video page)

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
- Note what each creator emphasizes or omits

### Analysis Template

```
## Video Analysis: [Title]
Channel: [Name] | Duration: [HH:MM:SS] | Date: [YYYY-MM-DD]

### Summary
[2-3 sentence overview]

### Key Points
1. [Timestamp] — [Point]
2. [Timestamp] — [Point]
...

### Notable Quotes
- "[Direct quote]" — [Context]

### Resources Mentioned
- [Tool/link/book mentioned in the video]

### Critical Assessment
- Strengths: [What the video gets right]
- Gaps: [What it misses or oversimplifies]
- Bias: [Any commercial or ideological slant]
```

## Phase 4: Deliver

Format output based on use case:

| Use Case | Format |
|----------|--------|
| Quick reference | Bullet-point summary |
| Study notes | Detailed notes with timestamps |
| Content creation | Key insights + quotable moments |
| Research | Comparative analysis across videos |
| Meeting prep | Executive summary + action items |

### Multi-Video Analysis

When analyzing several videos on the same topic:
1. Create a comparison matrix
2. Identify points of agreement and disagreement
3. Rank videos by depth, accuracy, and production quality
4. Recommend the best starting point for the user
