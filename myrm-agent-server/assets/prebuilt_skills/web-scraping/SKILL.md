---
name: web-scraping
description: >-
  Structured web scraping workflow using browser automation. Handles dynamic pages,
  pagination, anti-bot detection, and structured data extraction.
version: 1.0.0
category: data-collection
tags:
  - scraping
  - browser
  - data-extraction
  - automation
allowed-tools: browser_navigate_tool browser_interact_tool browser_snapshot_tool browser_extract_tool web_fetch_tool bash_code_execute_tool file_write_tool
contract:
  steps:
    - "Phase 1: Recon — analyze target page structure and data layout"
    - "Phase 2: Strategy — choose extraction method (static fetch vs browser automation)"
    - "Phase 3: Extract — navigate, interact, and extract structured data"
    - "Phase 4: Validate — verify data completeness and quality"
    - "Phase 5: Output — save in the requested format (JSON, CSV, etc.)"
  potential_traps:
    - description: "Getting blocked by anti-bot detection or rate limiting"
      mitigation: "Add delays between requests; respect robots.txt; use browser automation for JS-heavy sites"
      severity: high
    - description: "Extracting stale or incomplete data due to lazy loading"
      mitigation: "Scroll to trigger lazy loading; wait for dynamic content; verify element presence before extraction"
      severity: medium
  verification_steps:
    - step_id: data_complete
      description: "All expected data points are extracted"
      validation_method: "Compare extracted count against expected count; spot-check random samples"
      is_required: true
    - step_id: data_valid
      description: "Extracted data matches source page"
      validation_method: "Manually verify 3-5 random entries against the original page"
      is_required: true
  success_criteria: "Complete, accurate, and structured data extracted and saved"
  estimated_duration_seconds: 1200
---

# Web Scraping

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Web scraping requires careful planning to extract data reliably. Jumping straight to code without understanding the page structure leads to fragile scrapers that break immediately.

## Phase 1: Recon

Before writing any extraction code:

1. **Visit the target page** using `browser_navigate_tool`
2. **Take a snapshot** using `browser_snapshot` to understand the DOM structure
3. **Identify the data** — Where is the data? Tables? Lists? Cards? API responses?
4. **Check for pagination** — How many pages? URL pattern? "Load more" button?
5. **Check for dynamic content** — Is data loaded via JavaScript? Are there lazy-loaded sections?

### Key Questions

- Is the data available in a public API? (Check Network tab — often easier than scraping HTML)
- Does the page require authentication?
- Is there a `robots.txt`? Respect it.
- How frequently does the page structure change?

## Phase 2: Strategy

Choose the right approach:

| Scenario | Method |
|----------|--------|
| Static HTML, simple structure | `web_fetch_tool` + parse HTML |
| JavaScript-rendered content | Browser automation (`browser_navigate_tool` + `browser_interact_tool`) |
| Paginated results | Loop with URL pattern or "next" button |
| Data behind login | Browser automation with cookie handling |
| API available | Direct API calls (preferred — most reliable) |

### Decision Tree

```
Is there a public API?
├── Yes → Use API directly (most reliable)
└── No → Is content static HTML?
    ├── Yes → Use web_fetch_tool + parsing
    └── No → Use browser automation
```

## Phase 3: Extract

### Using `web_fetch_tool` (Static Pages)

```python
# Fetch and parse with Python
from html.parser import HTMLParser
# or use regex for simple patterns
```

### Using Browser Automation (Dynamic Pages)

1. **Navigate:** `browser_navigate_tool` to the target URL
2. **Wait:** Allow dynamic content to load
3. **Snapshot:** `browser_snapshot` to get current DOM state
4. **Interact:** Click pagination, expand sections, scroll for lazy loading
5. **Extract:** Parse the snapshot data for structured information

### Pagination Handling

```
For each page:
  1. Extract data from current page
  2. Check for "next" button or page link
  3. Navigate to next page
  4. Repeat until no more pages
```

### Rate Limiting

- Add 1-3 second delays between page requests
- Stop and report if receiving HTTP 429 or CAPTCHA challenges
- Never scrape faster than a human would browse

## Phase 4: Validate

After extraction, verify:

1. **Completeness** — Expected number of records vs actual
2. **Accuracy** — Spot-check 3-5 random entries against the source
3. **Format** — Data types correct? Dates parsed? Numbers numeric?
4. **Duplicates** — Any repeated entries from pagination overlap?

## Phase 5: Output

Save data in the requested format:

- **JSON** — Best for nested/hierarchical data
- **CSV** — Best for tabular data, spreadsheet import
- **Markdown table** — Best for quick viewing

Include metadata:
- Source URL
- Extraction timestamp
- Total record count
- Any known data gaps or issues
