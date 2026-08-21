---
name: web-project-seo-optimization
description: >-
  End-to-end technical SEO, on-page optimization, AI search readiness (LLMO), and actionable
  priority roadmap generation for web applications and content sites.
version: 1.0.0
category: marketing-growth
tags:
  - seo
  - web-audit
  - llmo
  - optimization
  - structured-data
  - sitemap
  - technical-seo
allowed-tools: browser_navigate_tool browser_snapshot_tool browser_extract_tool web_fetch_tool web_search_tool file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Reconnaissance — fetch robots.txt, sitemap.xml, and llms.txt; discover key site pages"
    - "Phase 2: Technical & On-Page Audit — inspect real rendered DOM for Title, Meta, Canonical, H1, JSON-LD, OpenGraph, hreflang, and dead links"
    - "Phase 3: AI Search Readiness (LLMO) — audit semantic HTML hierarchy, citation anchors, and llms.txt compatibility"
    - "Phase 4: Actionable Priority Roadmap Generation — output structured P0-P3 SEO-OPTIMIZATION-ROADMAP.md artifact"
    - "Phase 5: Verification & Quality Gate — verify all claimed defects with concrete DOM selectors/evidence and ensure no hallucinatory paths"
  potential_traps:
    - description: "Hallucinating site errors or claiming missing tags without real DOM inspection evidence"
      mitigation: "Every finding MUST cite the exact URL and extracted tag/attribute snippet as proof"
      severity: high
    - description: "Recommending keyword stuffing or spammy meta patterns penalized by search engines"
      mitigation: "Strictly adhere to helpful-content and E-E-A-T guidelines; emphasize user intent and readable copy"
      severity: high
    - description: "Overlooking AI search engines (Perplexity, ChatGPT Search, Claude) and focusing solely on legacy Googlebot"
      mitigation: "Always inspect llms.txt presence, clear semantic Markdown headings, and machine-readable JSON-LD entities"
      severity: medium
    - description: "Broken hreflang reciprocity causing international SEO cannibalization"
      mitigation: "Verify bidirectional hreflang links across all localized URL variants"
      severity: medium
  verification_steps:
    - step_id: evidence_backed_audit
      description: "Audit findings include concrete DOM evidence (selectors, status codes, or tag snippets)"
      validation_method: "Verify all listed defects reference actual extracted page content"
      is_required: true
    - step_id: roadmap_artifact_created
      description: "Structured SEO-OPTIMIZATION-ROADMAP.md artifact is written with P0-P3 prioritization"
      validation_method: "Check file exists in artifacts/ or workspace and contains categorized actionable tasks"
      is_required: true
    - step_id: no_dead_links_in_sample
      description: "Sampled internal links are validated for 200 OK status codes"
      validation_method: "Verify internal navigation targets return successful HTTP status"
      is_required: true
  success_criteria: "Comprehensive, evidence-based SEO audit with actionable P0-P3 roadmap and AI search readiness checklist"
  estimated_duration_seconds: 1200
---

# Web Project SEO & AI Search Optimization

## Overview

High-ranking websites require both technical excellence (crawlability, indexability, structured data) and high semantic clarity for both traditional search crawlers (Googlebot, Bingbot) and modern AI answer engines (Perplexity, ChatGPT, Claude).

This workflow conducts an evidence-driven, end-to-end SEO and LLMO audit, producing a prioritized, developer-ready `SEO-OPTIMIZATION-ROADMAP.md` artifact.

---

## Phase 1: Reconnaissance (Crawling & Discovery)

Before auditing individual pages, map the site's architecture:

1. **Robots & Sitemaps**:
   - Fetch `robots.txt` via `web_fetch_tool`: Check `Disallow` rules, `Crawl-delay`, and `Sitemap` declarations.
   - Fetch `sitemap.xml`: Verify XML syntax, URL freshness, and total indexed page count.
2. **AI Engine Declaration**:
   - Check if `/llms.txt` or `/llms-full.txt` exists to provide clean context for AI agents and LLM search.
3. **Core Page Discovery**:
   - Identify primary entry points: Homepage, Key Landing Pages, Documentation/Blog index, Pricing, and Product catalog.

---

## Phase 2: Technical & On-Page Audit

Navigate to each key URL with `browser_navigate_tool` and extract rendered DOM with `browser_snapshot_tool` or `browser_extract_tool`:

### 1. Title & Meta Descriptions
- **`<title>`**: Unique, 50–60 characters, primary keyword placed near the front, brand suffix.
- **`<meta name="description">`**: 120–160 characters, clear value proposition with a call-to-action.
- **`<meta name="robots">`**: Ensure production pages do NOT contain accidental `noindex, nofollow`.

### 2. Canonicalization & Multi-language (hreflang)
- **`<link rel="canonical" href="...">`**: Self-referencing on canonical pages; prevents duplicate content issues.
- **`hreflang`**: Check bidirectional tags (e.g., `en`, `zh`, `ja`, `x-default`) if multi-language is supported.

### 3. Heading Hierarchy (H1–H6)
- Exactly one `<h1>` per page containing the core topic/keyword.
- Logical nesting (`<h1>` → `<h2>` → `<h3>`), no skipped heading levels.

### 4. Structured Data (JSON-LD)
- Inspect `<script type="application/ld+json">`.
- Validate Schema.org types: `Organization`, `WebSite`, `SoftwareApplication`, `Article`, `FAQPage`, `BreadcrumbList`.

### 5. OpenGraph & Social Cards
- `og:title`, `og:description`, `og:image` (absolute URL, min 1200x630), `og:url`, `twitter:card`.

### 6. Media & Links
- All `<img>` tags have descriptive `alt` attributes.
- Internal navigation links (`<a href="...">`) must be crawlable HTML links (not javascript `onClick`).

---

## Phase 3: AI Search Readiness (LLMO)

Audit how easily AI search engines parse and cite your content:

1. **Markdown & Semantic Density**: Is key value information hidden in bloated JS widgets, or cleanly structured in readable text?
2. **Direct Answer Paragraphs**: Does the top of each page provide a crisp 2-3 sentence direct answer for informational queries?
3. **Entity Disambiguation**: Are company, author, and product entities clearly declared with schema markup?
4. **Machine Context (`/llms.txt`)**: Provide a concise `/llms.txt` summarizing product capabilities and documentation index.

---

## Phase 4: Actionable Priority Roadmap

Compile all findings into a structured `SEO-OPTIMIZATION-ROADMAP.md` artifact with clear priorities:

- **P0: Critical Blockers** (e.g. `noindex` on live pages, broken canonical tags, 404 links on primary menu, missing title).
- **P1: High-Impact Essentials** (e.g. missing meta descriptions, missing JSON-LD schema, invalid H1 hierarchy, missing OpenGraph image).
- **P2: Performance & User Experience** (e.g. missing image alt tags, sub-optimal internal linking, missing breadcrumbs).
- **P3: Strategic Growth & AI Optimization** (e.g. `/llms.txt` creation, content hub clustering, FAQ schema expansion).

---

## Phase 5: Verification & Delivery

1. Spot-check 3–5 reported issues against the live DOM to ensure zero false positives.
2. Ensure every task in the roadmap contains:
   - **Target URL / File**
   - **Current State (Evidence snippet)**
   - **Recommended Fix (Exact HTML/JSON-LD code sample)**
   - **Acceptance Criteria (How developer can verify)**
3. Save the artifact to `artifacts/SEO-OPTIMIZATION-ROADMAP.md` and present an executive summary to the user.
