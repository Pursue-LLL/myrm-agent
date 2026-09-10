---
name: viral-quote-discovery
description: "Discover, extract, score, and format high-impact, emotionally resonant viral quotes and punchlines from long-form text, transcripts, and research for social media syndication."
version: "1.0.0"
category: "creative"
tags:
  - viral-quotes
  - content-creation
  - punchline
  - copywriting
  - social-media
  - quote-extraction
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Viral Quote Candidate Discovery Skill (爆款金句候选发现与选题结构化提炼技能)

## Overview

A dedicated skill for mining, scoring, and synthesizing high-impact, memorable, and emotionally resonant **Viral Quotes & Punchlines** from long-form interview transcripts, research reports, books, podcasts, and executive speeches.

It transforms dense, linear source material into social-media-ready hook candidates and visual quote card assets.

---

## 4-Dimensional Viral Scoring Radar (四维金句传播势能评分雷达)

When analyzing raw text, evaluate potential quote candidates against these 4 weighted pillars (0-25 points each, Total 100):

```
1. Emotional Resonance (情绪共鸣度 · 25pts)
   ├── Does it trigger deep empathy, address a silent industry pain point, or articulate what people felt but couldn't express?
   └── Avoids generic motivational platitudes; focuses on grounded, authentic human experience.

2. Counter-Intuitive Contrast (反直觉认知差 · 25pts)
   ├── Does it challenge consensus, invert conventional wisdom, or reveal an unexpected paradox?
   └── Structural pattern: "Most think X, but the uncomfortable truth is Y."

3. Syntactic Economy (语言凝练与节律 · 25pts)
   ├── Is it concise (< 40 Chinese characters or < 25 English words)?
   └── Uses parallel structures, internal rhymes, antitheses, or tight cadence suitable for memorization.

4. Memetic & Shareability Potential (社交货币与传播载体 · 25pts)
   ├── Is someone proud or eager to repost this to signal taste, intelligence, or shared identity?
   └── Seamlessly translates into single-image quote cards, slide conclusions, or video punchlines.
```

---

## 4-Step Discovery Workflow (四步提炼流水线)

```
Step 1: Ingestion & Boundary Parsing (信源摄取与上下文切片)
   ├── Scan long-form transcripts, articles, or speech notes.
   └── Retain source timestamps, speaker names, and contextual paragraphs to prevent out-of-context distortions.
Step 2: Candidate Scoring & Filtering (候选筛选与四维评分)
   ├── Filter candidates scoring >= 75 points.
   └── Rank candidates into Tier 1 (Viral Gold, 90-100), Tier 2 (Solid Punchline, 80-89), and Tier 3 (Supporting Quote, 75-79).
Step 3: Repurposing Packaging (全渠道适配与选题衍生)
   ├── Pair each quote with a hook opening for X/Threads.
   ├── Generate an image layout recommendation (typography, background mood, focal point).
   └── Draft a follow-up expansion discussion prompt (2-3 sentences).
Step 4: Structured Deliverable Export (结构化交付物导出)
   └── Output standard `viral_quotes.md` or JSON card deck.
```

---

## Standard Output Contract (`viral_quotes.md`)

```markdown
# 💎 [选题名称/信源] 爆款金句候选与分发资产包

## 1. 核心金句精选 (Top Candidates)

### 🥇 [金句 #1] “代码是给机器读的执行逻辑，但架构是向未来的自己写的人性情书。”
- **综合势能得分**: 94/100 (情绪共鸣: 24 | 认知差: 23 | 凝练度: 24 | 传播力: 23)
- **原始出处**: 第 3 节 · 架构师面对面访谈 (14:32)
- **爆点机制剖析**: 将冰冷的底层代码与温暖的人性情书形成强烈反差，精准击中资深开发者的职业尊严与技术情怀。
- **推荐分发场景**:
  - **社交推文**: 作为 Thread 首条 Hook；
  - **视觉卡片**: 深色背景 + 居中大字排版（配黄色高亮关键词）；
  - **选题衍生**: 展开撰写《为什么说好的架构设计本质上是团队的人文关怀？》。

---

### 🥈 [金句 #2] “不要把流程的臃肿，包装成治理的严谨。”
- **综合势能得分**: 88/100 (情绪共鸣: 25 | 认知差: 21 | 凝练度: 22 | 传播力: 20)
- **原始出处**: 第 5 节 · 效能中台复盘会
- **爆点机制剖析**: 一针见血戳破形式主义痛点，自带犀利的职场话题度。
```

---

## Safety & Integrity Rules

1. **Context Fidelity (严禁断章取义)**: Never alter a quote's core meaning or fabricate words the speaker never uttered.
2. **Attribution**: Always explicitly credit the original speaker or publication.
3. **Actionable Follow-up**: Every extracted quote must have at least one concrete downstream repurposing recommendation.
