---
name: blog-monitoring
description: >-
  Monitor blogs, RSS feeds, and tech news sources for updates on specific topics.
  Extracts key developments, summarizes articles, and produces curated digests.
version: 1.0.0
category: research
tags:
  - monitoring
  - rss
  - news
  - blogs
  - content-curation
allowed-tools: web_search_tool web_fetch_tool bash_code_execute_tool file_write_tool memory_save_tool
contract:
  steps:
    - "Phase 1: Configure — define monitoring targets (keywords, sources, frequency)"
    - "Phase 2: Scan — fetch and filter content from target sources"
    - "Phase 3: Analyze — summarize and categorize findings"
    - "Phase 4: Digest — produce a structured monitoring report"
  potential_traps:
    - description: "Information overload from too many sources"
      mitigation: "Limit to 10-15 sources; apply strict relevance filtering before deep reading"
      severity: medium
    - description: "Missing important content behind paywalls"
      mitigation: "Note paywalled sources explicitly; search for alternative coverage"
      severity: low
  success_criteria: "Curated digest covering all significant developments in the monitored topics"
  estimated_duration_seconds: 900
---

# Blog Monitoring

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Staying current in fast-moving fields requires systematic monitoring. This skill automates the discovery, filtering, and summarization of content from blogs, news sites, and RSS feeds.

## Phase 1: Configure Monitoring

### Define Monitoring Scope

1. **Keywords** — what topics to track (e.g., "AI agents", "LLM inference")
2. **Sources** — which blogs/sites to monitor
3. **Frequency** — how often to check (daily, weekly)
4. **Priority** — what signals matter most (breaking news, deep analysis, tutorials)

### Source Categories

| Category | Examples | Check Frequency |
|----------|---------|-----------------|
| Official blogs | Company engineering blogs | Daily |
| Industry news | TechCrunch, The Verge, Hacker News | Daily |
| Expert blogs | Individual researchers, practitioners | Weekly |
| Aggregators | Reddit, Lobste.rs, dev.to | Daily |
| Research | arXiv, conference proceedings | Weekly |

### RSS Feed Discovery

For any site, try common RSS URL patterns:
- `site.com/feed`
- `site.com/rss`
- `site.com/feed.xml`
- `site.com/atom.xml`
- `site.com/index.xml`

Use `web_fetch_tool` to check if the URL returns valid XML/JSON feed content.

## Phase 2: Scan Sources

### Search Strategy

Use `web_search_tool` with time-filtered queries:
- `"keyword" site:blog.example.com` — specific source
- `"keyword" after:YYYY-MM-DD` — recent content only
- Hacker News: `site:news.ycombinator.com "keyword"`

### RSS / Atom feeds (known feed URLs)

When the source URL is a known RSS/Atom feed, use `web_fetch_tool` to retrieve it,
then extract from the response: title, link, publication date, and summary/description
for each `<item>` or `<entry>`. Prefer fetching only the feed URL (not individual articles)
in this phase to conserve tokens.

For unknown sites, use Phase 1 feed discovery patterns first.

### Filtering Rules

Prioritize items that:
- Contain multiple target keywords
- Are from high-authority sources
- Have significant engagement (comments, shares)
- Represent genuinely new information (not rehashes)

Skip items that:
- Are older than the monitoring window
- Are promotional/sponsored content
- Duplicate information already captured

## Phase 3: Analyze

For each relevant item:

1. **Fetch full content** using `web_fetch_tool`
2. **Extract key claims** — what's new or changed?
3. **Assess significance** — is this incremental or a major development?
4. **Identify connections** — how does this relate to other monitored topics?

### Significance Rating

| Rating | Criteria |
|--------|----------|
| HIGH | New product launch, major API change, breaking research, security vulnerability |
| MEDIUM | Feature update, new tutorial, industry analysis, community discussion |
| LOW | Minor update, opinion piece, rehash of known information |

## Phase 4: Produce Digest

### Digest Format

```
# [Topic] Monitoring Digest — [Date Range]

## Highlights
(Top 3-5 most significant developments, 1-2 sentences each)

## Detailed Coverage

### [Category 1]
- **[Title]** ([Source], [Date]) — [1-2 sentence summary] [Link]
- ...

### [Category 2]
- ...

## Trends & Patterns
(Cross-source observations, emerging themes)

## Action Items
(Things that may require response or further investigation)

## Sources Monitored
(List of all sources checked with last-check timestamps)
```

### Digest Quality Checklist

- [ ] All high-significance items included
- [ ] No duplicate coverage of the same development
- [ ] Links provided for all items
- [ ] Trends section identifies patterns across sources
- [ ] Action items are specific and actionable
