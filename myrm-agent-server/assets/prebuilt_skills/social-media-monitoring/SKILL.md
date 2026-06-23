---
name: social-media-monitoring
description: >-
  Monitor social media platforms (Xiaohongshu, Weibo, Twitter/X, etc.) for brand mentions,
  competitor activity, and trending topics. Uses browser automation to collect posts,
  performs sentiment analysis, and delivers structured intelligence reports.
version: 1.0.0
category: research
tags:
  - monitoring
  - social-media
  - sentiment-analysis
  - brand-tracking
  - competitive-intelligence
allowed-tools: browser_navigate browser_interact browser_snapshot browser_extract memory_save file_write_tool
contract:
  steps:
    - "Phase 1: Configure — define target brand, platforms, keywords, and monitoring scope"
    - "Phase 2: Collect — navigate social platforms via browser and extract relevant posts"
    - "Phase 3: Analyze — classify sentiment, detect trends, identify actionable insights"
    - "Phase 4: Report — produce a structured social media intelligence report"
  potential_traps:
    - description: "Platform anti-scraping detection"
      mitigation: "Add random delays (3-8s) between actions; mimic natural scrolling; limit to 20-30 posts per session"
      severity: medium
    - description: "Login session expired or not available"
      mitigation: "Check login status first via browser_snapshot; prompt user to re-login if needed"
      severity: medium
    - description: "Platform UI changes breaking extraction"
      mitigation: "Use semantic extraction via browser_extract with natural language queries instead of CSS selectors"
      severity: low
  success_criteria: "Structured report covering brand sentiment, notable mentions, and actionable insights from target platforms"
  estimated_duration_seconds: 600
---

# Social Media Monitoring

## Overview

Track brand reputation, competitor moves, and trending topics across social media platforms using browser automation. Unlike web-search-based monitoring, this skill navigates actual social platforms to access content that requires JavaScript rendering and login sessions.

## Phase 1: Configure Monitoring

### Required Information

1. **Brand/Topic** — what to monitor (brand name, product, topic)
2. **Platforms** — which social media to check (Xiaohongshu, Weibo, Twitter/X, Douyin, LinkedIn)
3. **Keywords** — search terms in the platform's language
4. **Scope** — time window (last 24h, last 7d) and post count limit (10-30 per platform)

### Platform Access Requirements

| Platform | URL | Login Required | Language |
|----------|-----|----------------|----------|
| Xiaohongshu | xiaohongshu.com | Yes | zh |
| Weibo | weibo.com | Yes | zh |
| Twitter/X | x.com | Yes | en/multi |
| Douyin | douyin.com | Yes | zh |
| LinkedIn | linkedin.com | Yes | en |

Before collecting, verify login status:
1. Use `browser_navigate` to open the platform
2. Use `browser_snapshot` to check if login prompt appears
3. If not logged in, inform the user and stop — do NOT attempt automated login

## Phase 2: Collect Posts

### Collection Strategy

For each platform and keyword:

1. **Navigate to search**
   - Use `browser_navigate` to open the platform's search page
   - Use `browser_interact` to enter keywords and submit search

2. **Wait and scroll**
   - Wait 3-5 seconds for results to load
   - Scroll down 2-3 times with 3-8 second random delays between scrolls
   - This mimics natural browsing behavior

3. **Extract post list**
   - Use `browser_extract` with a natural language query:
     "Extract all visible posts including: title/content preview, author name, publish date, like count, comment count, and post URL"

4. **Deep dive on notable posts** (optional, for high-engagement or negative posts)
   - Navigate to the individual post URL
   - Extract full content and top comments

### Anti-Detection Best Practices

- Keep total session under 5 minutes per platform
- Add random delays (3-8s) between every navigation action
- Limit to 20-30 posts per collection session
- Do NOT use rapid-fire clicking or scrolling
- If a CAPTCHA appears, stop and inform the user

## Phase 3: Analyze

### Sentiment Classification

For each collected post, classify sentiment:

| Sentiment | Indicators | Action Level |
|-----------|-----------|--------------|
| Strongly Positive | Praise, recommendation, "best", "love" | Note for marketing |
| Mildly Positive | Neutral-positive mention, sharing experience | Track |
| Neutral | Factual mention, no opinion expressed | Track |
| Mildly Negative | Minor complaint, suggestion for improvement | Monitor |
| Strongly Negative | Anger, demand refund, public complaint, viral criticism | **Alert immediately** |

### Trend Detection

Across all collected posts:
- Are there recurring themes or complaints?
- Has sentiment shifted compared to previous reports (if available in memory)?
- Any viral posts (unusually high engagement)?
- Competitor mentions alongside our brand?

### Key Metrics to Track

- Total mention count
- Positive/Negative ratio
- Top engagement posts (by likes + comments)
- New complaint themes
- Competitor comparison (if mentioned together)

## Phase 4: Report

### Report Structure

```
# Social Media Monitor — [Brand] — [Date]

## Summary
- Platforms checked: [list]
- Total posts analyzed: [N]
- Sentiment: [X% positive / Y% neutral / Z% negative]
- Alert level: [Normal / Attention / Critical]

## Key Findings
1. [Most important finding with source link]
2. [Second finding]
3. [Third finding]

## Sentiment Breakdown

| Platform | Posts | Positive | Neutral | Negative | Notable |
|----------|-------|----------|---------|----------|---------|
| ...      | ...   | ...      | ...     | ...      | ...     |

## Notable Mentions
### Positive
- [Post summary] — [Author], [Platform], [Engagement] [Link]

### Negative (Requires Attention)
- [Post summary] — [Author], [Platform], [Engagement] [Link]
  - Suggested response: [brief recommendation]

## Trends
- [Trend 1 observation]
- [Trend 2 observation]

## Competitor Activity
- [Any competitor mentions or activities observed]

## Recommendations
- [Actionable recommendation based on findings]
```

### Report Quality Checklist

- [ ] All specified platforms were checked
- [ ] Login status verified before collection
- [ ] Sentiment classification applied to every post
- [ ] Negative posts flagged with suggested responses
- [ ] Links provided for all notable mentions
- [ ] Trends identified across platforms (not just per-platform lists)
