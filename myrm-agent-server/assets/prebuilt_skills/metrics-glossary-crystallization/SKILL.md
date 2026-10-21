---
name: metrics-glossary-crystallization
description: >-
  Extract, formalize, and crystallize business metrics, KPIs, and operational definitions
  into the enterprise llm_wiki knowledge base. Enforces a 5-Dimensional Metric Specification
  (Standard Identifier & Aliases, Business Definition & Objectives, Formal Computation Logic & SQL,
  Data Lineage & Granularity, and Anti-Patterns & Known Pitfalls), preventing metric hallucination
  and cross-departmental definition drift.
version: 1.0.0
category: data-science
tags:
  - metrics
  - kpi
  - wiki
  - llm_wiki
  - knowledge-base
  - data-governance
  - business-intelligence
  - 口径沉淀
  - 业务指标
  - 数据治理
allowed-tools: file_read_tool file_write_tool wiki_ingest_tool wiki_query_tool wiki_apply_tool
contract:
  steps:
    - "Phase 1: Metric Discovery & Extraction — Identify business metrics, calculation discrepancies, and data tables in the conversation"
    - "Phase 2: 5-Dimensional Metric Specification — Draft metric card (Standard Identifier, Business Definition, Formal Computation Logic, Data Lineage, Anti-Patterns)"
    - "Phase 3: Stakeholder Disambiguation — Surface differences with closely related metrics (e.g. GMV vs Net Revenue, NRR vs GRR)"
    - "Phase 4: Wiki Crystallization & Ingestion — Publish structured markdown under docs/wiki/metrics/ and trigger Wiki compilation"
  potential_traps:
    - description: "Vague formula definitions lacking explicit boundary conditions (e.g. handling of discounts, taxes, or cancellations)"
      mitigation: "Require mathematical notation and explicit filtering conditions in SQL pseudo-code"
      severity: high
    - description: "Creating duplicate or conflicting metric entries in the knowledge base"
      mitigation: "Query existing wiki metrics via wiki_query_tool prior to publishing new definitions"
      severity: medium
    - description: "Omitting data lineage leading to unexecutable metrics"
      mitigation: "Include source database table and column names in the schema mapping section"
      severity: medium
  verification_steps:
    - step_id: five_dimensions_complete
      description: "Verify generated metric card contains all five required structural dimensions"
      validation_method: "Inspect metric card markdown structure against 5-Dimensional Metric Specification"
      is_required: true
    - step_id: disambiguation_addressed
      description: "Ensure potential traps and confusions with sister metrics are explicitly stated"
      validation_method: "Verify Anti-Patterns & Known Pitfalls section is populated"
      is_required: true
  success_criteria: "A formalized, unambiguous metric glossary specification published directly to the enterprise llm_wiki."
  estimated_duration_seconds: 240
---

# Metrics Glossary Wiki Crystallization Skill

## Overview

In enterprise data analytics, reporting, and executive reviews, few problems cause more friction than **metric definition drift**—where Marketing, Finance, and Product talk past each other because their definitions of "Active User", "CAC", or "Net Retention" diverge.

This skill governs the systematic extraction and crystallization of business metrics and KPIs into the workspace's self-evolving **`llm_wiki` Knowledge Base**.

---

## 5-Dimensional Metric Specification (五维业务指标权威口径规范)

Every metric crystallized into the Wiki must strictly define the following 5 dimensions:

### 1. Standard Identifier & Aliases (标准编码与同义词别名)
- **Standard Identifier**: e.g., `METRIC_NRR` (Net Revenue Retention / 净收入留存率)
- **Canonical Code**: Unique programmatic identifier for cross-referencing and database metrics catalogs.
- **Aliases & Synonyms**: Common colloquial terms, historical abbreviations, and departmental aliases.

### 2. Business Definition & Objectives (业务定义与核心目标)
- **Business Definition & Objectives**: Clear executive summary explaining what business health dimension this metric measures.
- **Boundary Scope**: What is strictly qualified and what is out-of-scope (e.g. excluding trial accounts, including signed expansion ARR).

### 3. Formal Computation Logic & SQL (严谨计算公式与代码口径)
- **Formal Computation Logic & SQL**: Exact mathematical equation paired with executable SQL pseudo-code:
  $$\text{NRR} = \frac{\text{Ending ARR from Cohort} + \text{Expansion} - \text{Contraction} - \text{Churn}}{\text{Starting ARR from Cohort}} \times 100\%$$
- **Reference SQL**:
  ```sql
  SELECT
    SUM(ending_arr + expansion_arr - contraction_arr - churn_arr) / SUM(starting_arr) AS nrr
  FROM subscription_cohorts
  WHERE cohort_month = :target_month;
  ```

### 4. Data Lineage & Granularity (数据血缘与源表时间切片)
- **Data Lineage & Granularity**: Source of truth tables, join relationships, update cadence (T+1 / Realtime), and timezone baselines (UTC+8).
- Primary fact tables: `core_billing.subscriptions`, `core_billing.invoices`.

### 5. Anti-Patterns & Known Pitfalls (负向用例与常见歧义陷阱)
- **Anti-Patterns & Known Pitfalls**: Explicit warnings regarding common misinterpretations and distinctions from adjacent metrics.
- Example: Distinction between NRR and Gross Retention Rate (GRR) where GRR strictly caps account expansion at 100%.

---

## Ingestion & Storage Protocol

1. Format the metric as a Markdown document named `docs/wiki/metrics/{metric_slug}.md`.
2. Ensure the frontmatter includes `type: metric` and relevant tags.
3. Call `wiki_ingest_tool` or `wiki_apply_tool` to persist the definition into the persistent `llm_wiki` vault.
4. Call `wiki_query_tool` to verify cross-linking with parent and child metrics.
