---
name: data-analysis
description: >-
  End-to-end data analysis workflow: ingest, clean, analyze, visualize, and report.
  Handles CSV, JSON, Excel, and database queries. Produces charts and actionable insights.
version: 1.0.0
category: data-science
tags:
  - data-analysis
  - visualization
  - statistics
  - insights
  - charts
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool
contract:
  steps:
    - "Phase 1: Ingest — load data and understand its structure"
    - "Phase 2: Clean — handle missing values, duplicates, type errors"
    - "Phase 3: Explore — summary statistics, distributions, correlations"
    - "Phase 4: Analyze — answer specific questions with appropriate methods"
    - "Phase 5: Visualize — create charts that communicate findings clearly"
    - "Phase 6: Report — structured insights with evidence and recommendations"
  potential_traps:
    - description: "Drawing conclusions from data without checking for outliers or bias"
      mitigation: "Always check distributions and outliers before statistical analysis"
      severity: high
    - description: "Creating visualizations that mislead (truncated axes, wrong chart types)"
      mitigation: "Start axes at zero for bar charts; use appropriate chart types for data type"
      severity: medium
  verification_steps:
    - step_id: data_quality
      description: "Data quality issues are identified and handled"
      validation_method: "Missing values, duplicates, and type errors are documented and resolved"
      is_required: true
    - step_id: findings_quantified
      description: "All findings include specific numbers, not vague statements"
      validation_method: "Every insight includes a metric (percentage, count, trend direction)"
      is_required: true
  success_criteria: "Clear insights backed by data with professional visualizations"
  estimated_duration_seconds: 1800
---

# Data Analysis

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Good analysis tells a story with data. Bad analysis dumps numbers without context. This workflow ensures every analysis produces actionable insights, not just statistics.

## Phase 1: Ingest

1. **Load the data** using Python (pandas):

```python
import pandas as pd
df = pd.read_csv("data.csv")  # or read_excel, read_json, etc.
```

2. **Understand the structure:**
   - `df.shape` — How many rows and columns?
   - `df.dtypes` — What are the column types?
   - `df.head()` — What does the data look like?
   - `df.describe()` — Basic statistics

3. **Clarify the question** — What specific questions should this data answer?

## Phase 2: Clean

Check and fix:

| Issue | Detection | Resolution |
|-------|-----------|------------|
| Missing values | `df.isnull().sum()` | Drop, fill (mean/median/mode), or flag |
| Duplicates | `df.duplicated().sum()` | Remove or investigate |
| Type errors | `df.dtypes` | Convert with `pd.to_datetime()`, `astype()` |
| Outliers | `df.describe()`, box plots | Investigate cause; cap, remove, or flag |
| Inconsistent formats | Visual inspection | Standardize (dates, categories, units) |

**Document every cleaning decision.** Future analysis depends on these choices.

## Phase 3: Explore

Generate summary statistics and visualizations:

1. **Distributions** — Histograms for numeric columns
2. **Correlations** — Heatmap of numeric correlations
3. **Categories** — Value counts for categorical columns
4. **Time trends** — Line charts if temporal data exists
5. **Segments** — Group by key dimensions and compare

## Phase 4: Analyze

Match the analysis method to the question:

| Question Type | Method |
|--------------|--------|
| "How much?" | Descriptive statistics (mean, median, percentiles) |
| "Is there a difference?" | Group comparison (t-test, ANOVA) |
| "Is there a relationship?" | Correlation, regression |
| "What changed?" | Time series, period-over-period |
| "What's unusual?" | Outlier detection, anomaly scoring |
| "What predicts?" | Regression, classification |

## Phase 5: Visualize

Choose the right chart:

| Data Type | Best Chart |
|-----------|-----------|
| Trend over time | Line chart |
| Comparing categories | Bar chart (horizontal for many categories) |
| Part of whole | Stacked bar or treemap (avoid pie charts) |
| Distribution | Histogram or box plot |
| Relationship | Scatter plot |
| Geographic | Map visualization |

### Chart Guidelines

- Title every chart clearly
- Label axes with units
- Use colorblind-safe palettes
- Start bar chart y-axis at zero
- Add data labels for key values

## Phase 6: Report

Structure findings:

```
## Key Findings
1. [Most impactful insight with numbers]
2. [Second most impactful insight]
3. [Third insight]

## Detailed Analysis
[Charts and supporting evidence]

## Data Quality Notes
[Any caveats, limitations, or cleaning decisions]

## Recommendations
[Actionable next steps based on findings]
```
