---
name: arxiv-research
description: >-
  Search, retrieve, and analyze academic papers from arXiv. Summarizes papers,
  extracts key contributions, compares methodologies, and produces structured
  literature reviews.
version: 1.0.0
category: research
tags:
  - arxiv
  - academic
  - papers
  - literature-review
  - science
allowed-tools: web_search_tool web_fetch_tool file_write_tool memory_save
contract:
  steps:
    - "Phase 1: Query — formulate effective arXiv search queries"
    - "Phase 2: Retrieve — fetch and parse paper abstracts and metadata"
    - "Phase 3: Analyze — deep-read selected papers and extract key findings"
    - "Phase 4: Synthesize — produce a structured summary or literature review"
  potential_traps:
    - description: "Only reading abstracts without checking methodology"
      mitigation: "For key papers, fetch full PDF link and read methodology section"
      severity: medium
    - description: "Missing recent preprints by searching too narrowly"
      mitigation: "Use multiple query variations and check 'recent' sort order"
      severity: medium
  success_criteria: "Structured analysis of relevant papers with clear contribution mapping"
  estimated_duration_seconds: 1800
---

# arXiv Research

## Overview

arXiv.org hosts over 2 million scientific preprints. This skill provides systematic workflows for searching, analyzing, and synthesizing academic papers.

## Phase 1: Query Formulation

### arXiv API Search

Use the arXiv API via `web_fetch_tool`:

```
https://export.arxiv.org/api/query?search_query=QUERY&start=0&max_results=20&sortBy=submittedDate&sortOrder=descending
```

### Query Syntax

| Operator | Example | Meaning |
|----------|---------|---------|
| `ti:` | `ti:transformer` | Title contains "transformer" |
| `au:` | `au:vaswani` | Author name |
| `abs:` | `abs:attention mechanism` | Abstract contains phrase |
| `cat:` | `cat:cs.CL` | Category (cs.CL = Computation and Language) |
| `AND` | `ti:llm AND abs:reasoning` | Both conditions |
| `OR` | `ti:GPT OR ti:LLaMA` | Either condition |

### Common Categories

| Code | Field |
|------|-------|
| cs.AI | Artificial Intelligence |
| cs.CL | Computation and Language (NLP) |
| cs.CV | Computer Vision |
| cs.LG | Machine Learning |
| cs.SE | Software Engineering |
| stat.ML | Machine Learning (Statistics) |

### Search Strategy

1. Start with a broad query: `abs:topic AND cat:cs.AI`
2. Note key terms from top results, refine query
3. Search by prolific authors in the field
4. Check "related papers" in arXiv listings

## Phase 2: Retrieve and Filter

For each paper, extract:

- **Title** and **Authors**
- **arXiv ID** (e.g., 2301.12345)
- **Abstract** — read carefully for relevance
- **Submission date** — prioritize recent work
- **PDF link** — `https://arxiv.org/pdf/ARXIV_ID`
- **HTML link** — `https://arxiv.org/html/ARXIV_ID` (when available, easier to parse)

### Relevance Filtering

Rate each paper (1-5):
- **Relevance** to the research question
- **Impact** (citation count if available, venue reputation)
- **Recency** (newer is generally better for active fields)

Select top 5-10 papers for deep analysis.

## Phase 3: Deep Analysis

For each selected paper, read and extract:

1. **Problem Statement** — What gap does this address?
2. **Key Contribution** — What's new or different?
3. **Methodology** — How did they approach it?
4. **Main Results** — Quantitative improvements, benchmarks
5. **Limitations** — What the authors acknowledge (or should)
6. **Relevance** — How does this connect to the research question?

### Paper Summary Template

```
## [Title] (arXiv:XXXX.XXXXX)
Authors: ...
Date: YYYY-MM-DD

**Problem:** [one sentence]
**Approach:** [one sentence]
**Key result:** [one sentence with numbers]
**Relevance:** [why this matters for our question]
```

## Phase 4: Synthesize

### Literature Review Structure

```
## Overview
(Research question and scope)

## Key Themes
(Group papers by approach/finding)

## Comparison Table
| Paper | Approach | Dataset | Key Metric | Result |
|-------|----------|---------|------------|--------|

## Open Questions
(What remains unsolved or debated)

## Recommendations
(Most promising directions based on evidence)

## References
(Full arXiv links for all cited papers)
```

### Synthesis Guidelines

- Identify agreements and disagreements between papers
- Note methodological trends (what approaches are gaining traction)
- Flag papers that contradict the mainstream narrative
- Distinguish established findings from preliminary results
