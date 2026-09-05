---
name: web-scraping
description: >-
  Enterprise-grade structured web scraping and paginated table harvesting workflow.
  Handles dynamic pages, anti-bot delays, multi-page table scraping with dual-sentinel loop guards,
  incremental disk caching, and standard CSV/Excel artifact generation.
version: 1.1.0
category: data-collection
tags:
  - scraping
  - browser
  - data-extraction
  - automation
  - pagination
  - tables
  - excel
  - csv
allowed-tools: browser_navigate_tool browser_interact_tool browser_snapshot_tool browser_extract_tool web_fetch_tool bash_code_execute_tool file_write_tool
contract:
  steps:
    - "Phase 1: Recon — analyze target page structure, tables, and pagination layout"
    - "Phase 2: Strategy — choose extraction method (static fetch vs browser automation)"
    - "Phase 3: Extract — navigate, interact, and harvest data with dual-sentinel pagination guard"
    - "Phase 4: Validate — verify data completeness, row counts, and sample accuracy"
    - "Phase 5: Output — stream into incremental disk cache and produce clean CSV/Excel Artifact"
  potential_traps:
    - description: "Getting blocked by anti-bot detection or rate limiting"
      mitigation: "Add 1-3s delays between page requests; respect robots.txt; use browser automation for JS-heavy sites"
      severity: high
    - description: "Extracting stale or incomplete data due to lazy loading"
      mitigation: "Scroll to trigger lazy loading; wait for dynamic content; verify element presence before extraction"
      severity: medium
    - description: "Infinite pagination loop on terminal pages with disabled or pseudo-active next buttons"
      mitigation: "Enforce Dual-Sentinel Guard: track first-row data fingerprint and bounded max page limit; break upon duplicate fingerprint"
      severity: critical
    - description: "Massive scraped table text blowing up LLM conversation context window"
      mitigation: "Stream each extracted page directly into sandbox temporary disk cache; return only lightweight metadata counters to conversation"
      severity: high
    - description: "Excel opening exported CSV with garbled non-English characters"
      mitigation: "Always write CSV using UTF-8 with BOM (utf-8-sig) to guarantee seamless spreadsheet opening across all platforms"
      severity: medium
  verification_steps:
    - step_id: data_complete
      description: "All expected data points and paginated rows are extracted"
      validation_method: "Compare extracted count against expected count; spot-check random samples"
      is_required: true
    - step_id: loop_guarded
      description: "Pagination terminated deterministically without runaway looping"
      validation_method: "Verify row fingerprint change or reach of page cap"
      is_required: true
    - step_id: data_valid
      description: "Extracted data matches source page"
      validation_method: "Manually verify 3-5 random entries against the original page"
      is_required: true
  success_criteria: "Complete, accurate structured data harvested and cleanly exported as a valid CSV/Excel artifact"
  estimated_duration_seconds: 1200
---

# Web Scraping & Paginated Table Harvesting

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Web scraping requires disciplined planning to extract data reliably. Jumping straight to scraping code without understanding page dynamics leads to fragile workflows, runaway loops, and corrupted outputs.

---

## Phase 1: Recon

Before extracting data:

1. **Visit the target page** using `browser_navigate_tool`.
2. **Inspect the layout** using `browser_snapshot_tool` to locate data containers (tables, cards, feeds).
3. **Identify pagination mechanism**:
   - Discrete **Next Page** button / page number links;
   - Asynchronous **Load More** button;
   - Continuous **Infinite Scroll / Virtual List** triggered by scrolling.
4. **Check for public API**: If network inspection reveals a direct REST API returning JSON, prefer direct fetch over heavy DOM parsing.

---

## Phase 2: Strategy

Select the optimal extraction approach based on page characteristics:

| Scenario | Primary Tool / Track | Pagination / Loading Pattern |
|:---|:---|:---|
| **Static HTML / Open Feed** | `web_fetch_tool` + Python parsing | URL parameter loops (`?page=1,2,3`) |
| **Client-Rendered Table (SPA)** | `browser_extract_tool` + `browser_interact_tool` | Next button with Sentinel Fingerprint |
| **Dynamic Lazy Feed** | `browser_interact_tool` (scroll) | Viewport wheel scroll + height checks |
| **Authenticated Portal / ERP** | Browser automation with existing session | Table scrape with incremental disk spill |

```
Is there a clean public/internal JSON API?
├── Yes → Use direct HTTP request (most reliable & token-efficient)
└── No → Is the content static HTML?
    ├── Yes → Use web_fetch_tool + Python parser
    └── No → Use browser automation with Dual-Sentinel pagination guard
```

---

## Phase 3: Extraction & Paginated Table Harvesting (Enterprise SOP)

When scraping multi-page tables (e.g., financial exchange rates, invoice lists, order records, directory databases):

### 1. Three-Dimensional Loading Modes

Select the exact interaction pattern matching the web page:

- **Mode A: Discrete Next Button**
  1. Call `browser_extract_tool(selector="table")` or extract target row items.
  2. Locate the "Next Page" button ref via snapshot.
  3. Click the button via `browser_interact_tool(action="click", ref=...)`.
  4. Wait for page stability or row container change before next extraction.

- **Mode B: Load More Button**
  1. Extract currently visible items.
  2. Click the "Load More" trigger ref.
  3. Verify that total rows increased or new cards appeared before continuing.

- **Mode C: Infinite Scroll / Virtual List**
  1. Extract currently visible viewport rows.
  2. Issue smooth scroll: `browser_interact_tool(action="scroll", direction="down", amount=800)`.
  3. Wait 1-2 seconds for new rows to hydrate.

---

### 2. Dual-Sentinel Loop Guard (Mandatory Anti-Dead-Loop Protocol)

Modern web frameworks often keep the "Next" button in the DOM even on the final page (only adding CSS opacity or `disabled` attributes). **Never rely solely on button presence to stop pagination.**

Always enforce the **Dual-Sentinel Guard**:

```
                              ┌───────────────────────────────┐
                              │    Extract Current Page       │
                              └──────────────┬────────────────┘
                                             │
                              ┌──────────────▼────────────────┐
                              │ Compute Sentinel Fingerprint  │
                              │ (First & Last Data Row Hash)  │
                              └──────────────┬────────────────┘
                                             │
                        ┌────────────────────┴────────────────────┐
                        ▼                                         ▼
            [Fingerprint Identical?]                    [Max Pages Reached?]
              (Repeated 2 consecutive)                 (Default limit: <= 10)
                        │                                         │
                        ├─────────────────┬───────────────────────┤
                        │                 │                       │
                       YES                NO                     YES
                        │                 │                       │
                        ▼                 ▼                       ▼
                  【STOP / BREAK】   【CLICK NEXT】          【STOP / BREAK】
                  Normal Final Page    Continue Loop          Hard Safety Cap
```

1. **Sentinel A (Row Fingerprint)**:
   - Extract a composite fingerprint from the first effective data row: `tbody > tr:first-child` (e.g., currency name + date, or order ID).
   - *Rule*: Ignore table header `<th>` rows to avoid static column false positives.
   - If the new page's row fingerprint is identical to the previous page, terminate the loop immediately.

2. **Sentinel B (Bounded Max Page Cap)**:
   - Always enforce an upper bound (default $\le 10$ pages unless explicitly requested by the user).
   - Never run unconstrained `while True` loops.

---

### 3. Incremental Disk Cache Protocol (Context & Token Protection)

Never accumulate thousands of raw table records in conversation memory.

1. **Stream Each Page to Disk**:
   - After extracting each page, immediately write or append rows to a sandbox scratch file (e.g., `.agent/scratch/table_data.csv`) using a lightweight Python script or `file_write_tool`.
2. **Concise Conversation Feedback**:
   - Return only compact metadata to the LLM turn:
     `[Page 3 Extracted: 25 rows appended to cache. Cumulative total: 75 rows. Sentinel verified.]`
   - This keeps the conversation context lean and guarantees **100% Prompt Cache hit rates**.
3. **Crash Recovery**:
   - If page 9 fails or encounters a network timeout, pages 1-8 are already safely persisted on disk.

---

### 4. Dual-Engine Output & Artifact Delivery

When pagination completes or reaches its termination condition, compile the cached data into a polished delivery artifact:

- **Engine 1: Standard Library Zero-Dependency Baseline (Primary)**
  Always guarantee export via Python's built-in `csv` module with UTF-8 BOM encoding (`encoding='utf-8-sig'`). This ensures Microsoft Excel, Apple Numbers, and Google Sheets open the file immediately with zero encoding glitches.
  ```python
  import csv

  with open("harvested_records.csv", "w", encoding="utf-8-sig", newline="") as f:
      writer = csv.DictWriter(f, fieldnames=headers)
      writer.writeheader()
      writer.writerows(all_rows)
  ```

- **Engine 2: Enhanced XLSX Formatter (Optional)**
  If `openpyxl` is available in the sandbox, optionally format as `.xlsx` with bold header styling, frozen top panes, and auto-adjusted column widths.

- **System Artifact Registration**:
  Place the final file in the project workspace or designated output directory to trigger the WebUI Artifact card, enabling the user to preview or download the spreadsheet with one click.

---

## Phase 4: Validation & Quality Control

Before presenting results to the user:

1. **Row Count Audit**: Verify that the cumulative row count matches the sum of page batches.
2. **Column Consistency**: Ensure no shifted columns or missing headers across pages.
3. **Encoding Check**: Confirm non-ASCII text (Chinese, Japanese, accented characters) is cleanly preserved.
4. **Summary Presentation**: Report source URL, total pages harvested, total record count, and file download path.
