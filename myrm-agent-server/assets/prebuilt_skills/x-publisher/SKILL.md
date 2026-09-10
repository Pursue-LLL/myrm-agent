---
name: x-publisher
description: >-
  Schedule, format, simulate, and safely publish single posts and multi-part threads to Twitter / X.
  Enforces 280-character thread segmentation, hook engagement rules, anti-spam spacing, and mandatory
  Human-In-The-Loop (HITL) pre-publish approval gates with complete payload preview.
version: 1.0.0
category: content-marketing
tags:
  - twitter
  - x
  - social-media
  - publishing
  - scheduling
  - hitl-gate
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool ask_question_tool
contract:
  steps:
    - "Phase 1: Composition & Thread Splitting — structure text into high-impact hook and numbered 280-char chunks (1/N, 2/N)"
    - "Phase 2: Pre-flight Quality & Compliance Audit — verify character limits, media attachments, clean URLs, and mention tags"
    - "Phase 3: Scheduling & Anti-Spam Spacing — calculate optimal posting slot or interval spacing to protect account reputation"
    - "Phase 4: Mandatory HITL Signoff & Execution — present complete tweet preview and require explicit user confirmation before release"
  potential_traps:
    - description: "Splitting sentences awkwardly across tweets or exceeding 280 characters in a single chunk"
      mitigation: "Calculate UTF-8 code point length (counting URLs as 23 chars per t.co spec); split at natural sentence punctuation"
      severity: high
    - description: "Unattended or accidental publication without human operator confirmation"
      mitigation: "Strict HITL invariant: never trigger live publish API/webhook without explicit ask_question_tool confirmation"
      severity: critical
    - description: "Burst posting multiple threads in short intervals causing shadowbanning"
      mitigation: "Enforce minimum 30-minute spacing between thread bursts and flag suspicious cadences"
      severity: medium
  verification_steps:
    - step_id: character_budget_audit
      description: "Verify that every tweet in the thread does not exceed 280 characters including numbering and hashtags"
      validation_method: "Length calculation per segment <= 280"
      is_required: true
    - step_id: hook_strength_audit
      description: "Verify the first tweet contains an engaging takeaway hook or thesis"
      validation_method: "Check first tweet has thesis/hook without trailing filler words"
      is_required: true
    - step_id: hitl_prepublish_approval
      description: "Present full payload preview and ask for explicit publish confirmation via ask_question_tool"
      validation_method: "Require confirmation before transitioning state to SCHEDULED or PUBLISHED"
      is_required: true
  success_criteria: "A polished, compliant, and verified Twitter/X single post or thread ready for immediate dispatch or queued scheduling after human signoff"
  estimated_duration_seconds: 400
---

# Twitter / X Post & Thread Publisher with Closed-Loop Quality Gate

## Overview

The `x-publisher` skill governs the creation, thread splitting, timing scheduling, and final signoff for content destined for Twitter / X. It bridges the gap between draft copy and live publication while eliminating high-risk blunders: truncated threads, runaway automated posts, missing media, and spammy burst behavior.

---

## 1. Twitter / X Mechanics & Sizing Rules

- **Standard Character Limit**: 280 characters per tweet (Unicode characters: ASCII=1 char, CJK characters=2 chars).
- **Link Shortening**: All web URLs are wrapped by X's `t.co` shortener and consume exactly **23 characters**, regardless of original URL length.
- **Media Attachments**: Up to 4 images, 1 GIF, or 1 video per tweet.
- **Thread Formatting**: Numbered indicator at the end or start of each tweet (e.g. `1/5`, `2/5` ... `5/5`).
- **First Tweet (The Hook)**: Must provide an irresistible curiosity gap, surprising metric, or clear thesis. No wasted introductory pleasantries ("Hey guys", "In this thread I will...").
- **Final Tweet (CTA & Retweet Bait)**: Summarize the key takeaway, invite discussion, and provide a single link or bookmark prompt.

---

## 2. Four-Phase Publishing SOP

### Phase 1: Content Composition & Thread Segmentation
1. Analyze whether the message fits in a **Single Tweet** (≤280 chars) or requires a **Thread** (2 to 10 tweets).
2. For threads:
   - Break content at natural semantic boundaries (paragraph or sentence endings).
   - Append `[x/N]` numbering.
   - Ensure each individual tweet provides standalone value even if quoted separately.

### Phase 2: Pre-Flight Compliance & Quality Gate
Audit every chunk against the following checklist:
- [ ] Length check: UTF-8 length ≤ 280 characters (taking 23-char URL rule into account).
- [ ] Hashtag discipline: Maximum 1-2 relevant hashtags per thread (0 on the hook tweet).
- [ ] Visual asset anchors: Specify image specs (16:9 for single image, 1:1 for 4-grid).
- [ ] Link placement: Primary links placed in tweet 2 or the final tweet to preserve algorithmic reach.

### Phase 3: Scheduling & Spacing
- Target high-engagement time windows (08:30, 12:30, 19:30 local audience time).
- If scheduling multiple items, enforce an **anti-spam spacing invariant**: minimum 30 minutes between tweets and 4 hours between threads.

### Phase 4: Mandatory Human-In-The-Loop (HITL) Signoff
**Zero-Unattended-Publish Rule**:
The agent must never mark a post as published or call outward webhooks without explicit user approval.
1. Render a clean visual preview of the entire thread with character counters.
2. Call `ask_question_tool` (or present a structured choice) asking the user:
   - `发布确认 (Confirm Publish)`: Approve immediate send or scheduled queue.
   - `微调修改 (Modify)`: Adjust copy or tone.
   - `暂存草稿 (Save as Draft)`: Store in `.myrm/drafts/` for later.

---

## 3. Standard Thread Deliverable Contract

```markdown
### 🐦 Twitter / X Thread Preview

**主题 (Topic)**: Myrm 技能工具链自动化排期与发布闭环  
**推文总数 (Total Tweets)**: 3 篇  
**发布状态 (Status)**: PENDING_CONFIRMATION (等待人工审核)

---

**[1/3] Hook Tweet** (218 / 280 chars)
> Most AI agents fail in production not because of model capability, but because of unverified outputs.
> 
> Here is how we engineered 4-dimensional quality gates into automated document generation and social scheduling:
> 
> [1/3]

---

**[2/3] Technical Core** (246 / 280 chars)
> 1. Plan-phase Thesis Gate: Every slide or article headline must state an opinionated takeaway.
> 2. Zero-CDN Invariant: Self-contained HTML artifacts with local state persistence.
> 3. HITL Confirmation: Automated webhooks paused until operator signoff.
> 
> [2/3]

---

**[3/3] Takeaway & CTA** (182 / 280 chars)
> True autonomy requires deterministic guardrails.
> 
> What guardrail has saved your production AI pipeline the most?
> 
> Drop your thoughts below or bookmark this framework! 🔖
> 
> [3/3]
```
