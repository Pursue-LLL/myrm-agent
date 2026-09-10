---
name: financial-business-analysis
description: >-
  Authoritative financial and business analysis specialty suite. Ingests official financial
  filings (10-K, 10-Q, annual reports, prospectuses), performs Python-based inter-statement
  reconciliation (balance sheet, income statement, cash flow), and compiles structured 6-dimensional
  institutional-grade business analysis reports with visualization artifacts.
version: 1.0.0
category: business-intelligence
tags:
  - finance
  - financial-analysis
  - business-intelligence
  - 10-K
  - annual-report
  - valuation
  - due-diligence
  - audit-reconciliation
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool web_search_tool web_fetch_tool
contract:
  steps:
    - "Phase 1: Ingest & Source Gate — retrieve official disclosure documents (SEC EDGAR, HKEXnews, CnInfo, SSE/SZSE, company IR) and validate source authenticity"
    - "Phase 2: Code-Driven Reconciliation — extract financial tables and execute Python scripts to verify 3-statement balancing and calculate key financial ratios"
    - "Phase 3: 6-Dimensional Analysis — analyze revenue/growth, profitability & DuPont decomposition, balance sheet health, competitive moat, unit economics, and operational risks"
    - "Phase 4: Synthesis & Artifact Export — generate institutional-grade markdown report, visualization charts (Mermaid/ECharts/Matplotlib), and audit appendix"
  potential_traps:
    - description: "Relying on mental arithmetic or LLM parametric estimation for financial metrics leading to arithmetic hallucinations"
      mitigation: "Strictly execute Python scripts in sandbox to compute CAGR, ROE, FCF, and reconciliation equations"
      severity: high
    - description: "Uncritical ingestion of secondary media summaries or unverified rumors as factual financial numbers"
      mitigation: "Enforce official filing whitelist (SEC EDGAR, official IR, audited regulatory filings) as primary source"
      severity: high
    - description: "Applying public-company 3-statement models to non-public startups, causing broken inferences or fabricated tables"
      mitigation: "Trigger non-public entity qualitative fallback gate: pivot to unit economics, funding history, and qualitative moat analysis"
      severity: medium
  verification_steps:
    - step_id: three_statement_reconciliation
      description: "Balance sheet identity (Assets = Liabilities + Equity) and cash reconciliation are verified via Python code"
      validation_method: "Audit code executed and delta confirmed == 0 or explicitly footnoted with non-GAAP variance"
      is_required: true
    - step_id: unit_and_currency_normalization
      description: "Currency denominations (USD/RMB/EUR) and units (Thousands/Millions/Billions) are standardized throughout report"
      validation_method: "Header metadata confirms normalized base currency and scale"
      is_required: true
  success_criteria: "Institutional-grade financial and business analysis report with audited numbers, 6-dimensional breakdown, charts, and executable verification appendix"
  estimated_duration_seconds: 1200
---

# Financial & Business Analysis Specialty Suite

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

High-stakes financial and business analysis requires absolute numerical integrity, rigorous inter-statement logic, and institutional-grade depth. General LLMs frequently hallucinate arithmetic, confuse financial metrics, or fail to cross-validate balance sheet identities.

The `financial-business-analysis` suite enforces strict audit rigor:
1. **Official Disclosure Ingestion**: Direct targeting of regulatory filings (SEC 10-K/10-Q, HKEX, CnInfo/巨潮, Official IR).
2. **Sandbox Python Reconciliation**: Computational verification of all CAGR, DuPont formulas, and Cash Flow reconciliations via code execution.
3. **6-Dimensional Analysis Framework**: Comprehensive coverage from executive summary to risk stress-testing.
4. **Transparent Audit Trail**: Every core metric is tied back to official filing source citations and verifiable calculation scripts.

## Core Workflow Phases

### Phase 1: Ingest & Source Gate
- Locate official audited filings following `references/financial-audit-sop.md`.
- Extract raw financial tables (Balance Sheet, Income Statement, Statement of Cash Flows, Segment Revenue).
- If analyzing a non-public/startup entity, activate the **Non-Public Qualitative Fallback SOP**.

### Phase 2: Python Code-Driven Reconciliation
- Generate and execute Python verification script via `bash_code_execute_tool`.
- Verify fundamental accounting identities:
  - $Assets = Liabilities + Shareholders' Equity$
  - $Ending Cash - Beginning Cash = Net Change in Cash$
  - $Operating Cash Flow \approx Net Income + Non-Cash Charges - \Delta NWC$
- Calculate core financial ratios (Gross Margin, Operating Margin, ROE/DuPont, FCF, Current Ratio, Debt-to-Equity).

### Phase 3: 6-Dimensional Business & Financial Synthesis
Follow the institutional structure defined in `references/financial-report-template.md`:
1. **Executive Summary & Investment/Health Rating**
2. **Revenue Dynamics & Segment Growth**
3. **Profitability Quality & DuPont Decomposition**
4. **Solvency, Liquidity & Capital Structure**
5. **Competitive Moat & Unit Economics**
6. **Downside Risks & Scenario Stress Testing**

### Phase 4: Artifact Generation & Deliverable Packaging
- Render charts using Mermaid, ECharts, or Matplotlib scripts.
- Export clean Markdown and trigger PDF compilation via `pdf-generator` if requested.
- Register all artifacts to `DeliverablesBoard` with the Python calculation script appended as an audit log.

## Reference Guides

- `references/financial-report-template.md` — 6-dimensional report structure & visualization templates
- `references/financial-audit-sop.md` — Official source retrieval, 3-statement reconciliation SOP, and non-public entity fallback rules
