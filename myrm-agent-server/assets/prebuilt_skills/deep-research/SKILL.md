---
name: deep-research
description: >-
  Systematic deep research workflow for producing comprehensive, evidence-based
  reports. Covers literature discovery, data collection, cross-validation, and
  structured report generation with proper citations.
version: 1.0.0
category: research
tags:
  - research
  - analysis
  - report
  - investigation
  - literature-review
allowed-tools: web_search_tool web_fetch_tool file_write_tool file_read_tool memory_search_tool memory_save_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Scope Definition — clarify research question, boundaries, deliverables"
    - "Phase 2: Discovery — systematic multi-source search with diverse queries"
    - "Phase 3: Deep Dive — extract and analyze primary sources in detail"
    - "Phase 4: Cross-Validation — verify claims across multiple independent sources"
    - "Phase 5: Synthesis — structure findings into a comprehensive report"
  potential_traps:
    - description: "Accepting claims from a single source without cross-validation"
      mitigation: "Every major claim must be verified by at least 2 independent sources"
      severity: high
    - description: "Getting lost in tangential topics during discovery"
      mitigation: "Constantly check findings against the original research question"
      severity: medium
  verification_steps:
    - step_id: scope_clear
      description: "Research question and deliverable format are clearly defined"
      validation_method: "User confirms the research scope before proceeding"
      is_required: true
    - step_id: sources_diverse
      description: "Findings draw from multiple independent sources"
      validation_method: "At least 5 distinct sources cited in the final report"
      is_required: true
  success_criteria: "Comprehensive report with verified claims, proper citations, and actionable insights"
  estimated_duration_seconds: 3600
---

# Deep Research

## Overview

Shallow research produces shallow results. This workflow enforces systematic, multi-source investigation to produce reports that are evidence-based, properly cited, and actionable.

**Core principle:** Every claim must have evidence. Every conclusion must have multiple sources.

## Phase 1: Scope Definition

Before searching anything, establish clear boundaries.

1. **Clarify the research question** — What specific question are we answering?
2. **Define deliverables** — What format? Executive summary? Comparison table? Full report?
3. **Set boundaries** — Time frame? Geographic scope? Industry vertical?
4. **Identify known context** — What does the user already know? What gaps exist?

If the request is vague, ask one focused clarifying question before proceeding.

## Phase 2: Discovery

Systematic multi-source search:

### Search Strategy

1. **Start broad** — Use `web_search_tool` with 3-5 diverse queries on the topic
2. **Identify key sources** — Academic papers, industry reports, expert blogs, official documentation
3. **Follow citations** — Good sources reference other good sources
4. **Check recency** — Prioritize recent sources for fast-moving topics

### Source Quality Hierarchy

| Priority | Source Type | Trust Level |
|----------|-----------|-------------|
| 1 | Primary data / Official documentation | High |
| 2 | Peer-reviewed papers / Industry reports | High |
| 3 | Expert analysis / Established publications | Medium |
| 4 | Blog posts / Community discussions | Low — verify claims |

### Discovery Checklist

- [ ] At least 3 different search queries used
- [ ] Sources span multiple types (not all from one blog)
- [ ] Recent sources prioritized for current topics
- [ ] Key terminology and taxonomy identified

## Phase 3: Deep Dive

For each important source:

1. **Use `web_fetch_tool` to extract full content**
2. **Identify key claims and data points**
3. **Note the evidence quality** — Is it opinion, anecdote, or data-backed?
4. **Extract quotable passages** with source attribution
5. **Save important findings** using `memory_save_tool` for later synthesis

### Reading Strategy

- Don't skim — read methodology sections carefully
- Note sample sizes, timeframes, and limitations
- Identify conflicts between sources
- Flag information gaps explicitly

## Phase 4: Cross-Validation

**Every major claim must be verified by at least 2 independent sources.**

1. For each key finding, search for confirming or contradicting evidence
2. If sources conflict, investigate why — different methodologies? Different timeframes?
3. Distinguish: verified facts → inferences → speculation
4. Grade confidence: High (3+ sources agree) / Medium (2 sources) / Low (single source)

## Phase 5: Synthesis

Structure the report:

```
## Executive Summary
(2-3 paragraphs: key findings, implications, recommendations)

## Key Findings
(Structured sections with evidence and citations)

## Analysis
(Patterns, trends, comparisons — with data)

## Limitations
(What this research doesn't cover, information gaps)

## Recommendations
(Actionable next steps, prioritized)

## Sources
(All sources cited with URLs and access dates)
```

### Writing Guidelines

- Lead with insights, not descriptions
- Quantify findings (percentages, trends, anomalies)
- Use comparison tables for multi-option analyses
- Flag confidence levels for each major conclusion
- Cite sources inline: "According to [Source Name], ..."
