---
name: viral-quote-discovery-workflow
description: >-
  Systematic viral hook, counter-intuitive insight, and memorable quote discovery pipeline.
  Surveys social discussions, industry blogs, and technical newsletters to unearth high-resonance
  soundbites, analyzes viral mechanics, and derives channel-tailored derivatives for X, Xiaohongshu, and WeChat.
version: 1.0.0
category: creative
tags:
  - viral-quote
  - hook-discovery
  - content-strategy
  - copywriting
  - social-media
  - growth
  - 爆款金句
  - 选题挖掘
  - 社交传播
  - 钩子公式
allowed-tools: file_read_tool file_write_tool web_search_tool
contract:
  steps:
    - "Phase 1: Multi-Channel Trending Survey — search high-engagement discussions across tech and industry sources (last 24-48h)"
    - "Phase 2: Resonance & Hook Analysis — filter soundbites with counter-intuitive perspectives, emotional tension, or mnemonic brevity"
    - "Phase 3: Viral Mechanics Deconstruction — break down why each quote works (hook archetype, audience identity, friction point)"
    - "Phase 4: Omnichannel Derivative Synthesis — generate platform-native spins for X threads, Xiaohongshu posters, and newsletter intros"
    - "Phase 5: Golden Quote Library Crystallization — save curated quotes into structured markdown artifact `docs/marketing/viral_quotes_{topic}.md`"
  potential_traps:
    - description: "Selecting generic clichés or corporate platitudes that lack virality or controversy"
      mitigation: "Enforce the 'Surprise Threshold': candidate quotes must challenge consensus or reframe common knowledge"
      severity: high
    - description: "Quoting out of context or misattributing quotes without source verification"
      mitigation: "Include source link, speaker identity, and context paragraph for every extracted quote"
      severity: medium
  verification_steps:
    - step_id: trend_survey_executed
      description: "Ensure candidate quotes are gathered from live discussions or verified corpus"
      validation_method: "Extracted quotes include citation and original context"
      is_required: true
    - step_id: omnichannel_derivations_present
      description: "Every top quote has adapted variants for X, Xiaohongshu, and WeChat"
      validation_method: "Inspect output for 3 distinct platform adaptation blocks"
      is_required: true
    - step_id: quote_library_persisted
      description: "Curated quotes saved into markdown file"
      validation_method: "file_write_tool outputs structured document"
      is_required: true
  success_criteria: "A structured, insightful viral quote candidate report with platform-tailored adaptations and clear hook deconstructions"
  estimated_duration_seconds: 240
---

# Viral Quote Candidate Discovery & Hook Synthesis Workflow

## Overview

High-performing content is anchored by memorable, counter-intuitive, or emotionally resonant soundbites. This skill executes an end-to-end pipeline to discover, deconstruct, and adapt viral quotes and golden hooks across modern distribution channels.

---

## 4-Stage Discovery Architecture

```
┌────────────────────────────────────────────────────────┐
│            Viral Quote Discovery Workflow              │
├──────────────────────────┬─────────────────────────────┤
│ 1. Trend & Discussion    │ 2. Hook & Friction Filter   │
│    - Social feeds & RSS  │    - Counter-intuitive      │
│    - Top engagement hits │    - Identity resonance     │
├──────────────────────────┼─────────────────────────────┤
│ 3. Viral Deconstruction  │ 4. Omnichannel Adaptations  │
│    - Psychology trigger  │    - X / Twitter Hook       │
│    - Friction point      │    - Xiaohongshu Cover      │
│    - Structural formula  │    - WeChat Title / Intro   │
└──────────────────────────┴─────────────────────────────┘
```

### 1. The 5 Viral Hook Archetypes

When mining soundbites from target feeds, identify which archetype each candidate represents:

1. **The Contrarian Truth (反共识真相)**:
   - *Example*: "More code is a liability, not an asset." / "Your best hire this year might not be a human."
2. **The Hard Pill to Swallow (扎心痛点)**:
   - *Example*: "You don't have a strategy problem; you have an execution avoidance problem."
3. **The Elegant Reframing (认知升维)**:
   - *Example*: "Prompt engineering isn't coding; it's delegating to the smartest intern who never sleeps."
4. **The High-Stakes Paradox (极端悖论)**:
   - *Example*: "The fastest way to ship quality software is to slow down code generation."
5. **The Micro-SOP Gold Nugget (极简方法论)**:
   - *Example*: "If a bug isn't reproducible in 3 minutes, delete the test and start from scratch."

---

## Output Contract (`docs/marketing/viral_quotes_{topic}.md`)

The generated artifact must follow this structured schema:

```markdown
# 爆款金句与高潜选题库 · [主题名称]

## 1. 核心高潜金句精选 (Top Viral Candidates)

### 候选 1: [金句摘要]
- **原始引文**: "..."
- **引文出处**: [发言人 / 平台 / 链接]
- **爆款机制拆解**:
  - **钩子原型**: [反共识 / 痛点暴击 / 认知重构]
  - **心理共鸣点**: [击中哪些群体的何种隐秘情绪]
  - **传播阻力评级**: [极低 / 容易引发辩论]

#### 多平台衍生应用 (Omnichannel Derivatives)
- **X (Twitter) 串推首推**:
  > [280 字以内强钩子 + 设问]
- **小红书 (RED) 封面大字 & 副标**:
  - 主标题: [8-12 字吸睛金句]
  - 副标题: [痛点解决方案]
- **微信公众号选题与切角**:
  - 推荐推文标题: [悬念式 / 深度分析式]
  - 开篇破冰段落: [从金句切入引发读者好奇]
```
