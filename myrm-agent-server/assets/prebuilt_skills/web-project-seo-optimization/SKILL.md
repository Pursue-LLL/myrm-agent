---
name: web-project-seo-optimization
description: >-
  Systematic Web project & site SEO optimization workflow. Performs automated P0-P3 audit,
  meta tag remediation, JSON-LD structured data generation, i18n hreflang validation,
  dead-link & soft-404 detection, dynamic sitemap/robots.txt generation, and roadmap artifact output.
version: 1.0.0
category: optimization
tags:
  - seo
  - web
  - optimization
  - audit
  - sitemap
  - metadata
allowed-tools: file_read_tool file_write_tool file_edit_tool glob_tool grep_tool bash_code_execute_tool web_fetch_tool web_search_tool browser_navigate_tool browser_snapshot_tool browser_extract_tool
contract:
  steps:
    - "Phase 1: Recon — detect framework architecture (Next.js/Astro/Vite/static), route structure, and target scope"
    - "Phase 2: Plan — generate SEO-OPTIMIZATION-ROADMAP.md artifact with prioritized P0–P3 checklist"
    - "Phase 3: Audit — scan meta tags, Open Graph, Twitter Cards, JSON-LD schemas, alternate hreflangs, and dead links"
    - "Phase 4: Remediate — in-place code edits, metadata export fixes, sitemap/robots generation, and link repairs"
    - "Phase 5: Verify — execute link validator probe, confirm zero dead links / zero soft-404s, and output diff summary"
  potential_traps:
    - description: "Keyword stuffing or generating hidden text leading to search engine penalties"
      mitigation: "Strictly adhere to Google Search Central guidelines and natural readability"
      severity: high
    - description: "Overwriting framework-native dynamic metadata APIs with static HTML tags"
      mitigation: "Detect framework (e.g. Next.js App Router generateMetadata) and export structured metadata objects"
      severity: high
    - description: "SPA soft-404 false negatives (HTTP 200 returning 'Page Not Found' DOM)"
      mitigation: "Combine HTTP status check with DOM heading/title inspection"
      severity: medium
  verification_steps:
    - step_id: roadmap_artifact_created
      description: "SEO-OPTIMIZATION-ROADMAP.md created with explicit P0-P3 items"
      validation_method: "Verify file existence in workspace"
      is_required: true
    - step_id: zero_dead_links
      description: "All internal and external links are verified valid"
      validation_method: "Run link validator probe and check zero 404 or broken references"
      is_required: true
    - step_id: structured_data_valid
      description: "JSON-LD schema complies with Schema.org standards"
      validation_method: "Validate JSON syntax and required Schema.org fields"
      is_required: true
  success_criteria: "Complete SEO audit roadmap delivered, code remediated according to framework standards, and zero dead links verified"
  estimated_duration_seconds: 1800
---

# Web Project SEO Optimization

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Overview

Web Project SEO Optimization transforms raw web projects into high-ranking, standards-compliant, crawlable digital properties. Instead of unstructured ad-hoc suggestions, this workflow follows a deterministic, 5-phase engineering protocol.

---

## Phase 1: Reconnaissance (Architecture & Scope Detection)

1. **Framework & Router Discovery**:
   - Next.js (App Router `app/` vs Pages Router `pages/` vs Static Export)
   - Astro (`src/pages/`, `astro-seo`, content collections)
   - Nuxt / SvelteKit / Remix / Vite SPA / Pure HTML
2. **Page & Route Cataloging**:
   - Use `glob_tool` to list all page entry points.
   - Extract internal linking patterns and public static assets (favicons, logos, social share images).
3. **i18n & Canonical Baseline**:
   - Determine if multi-language routes exist (e.g., `/en/`, `/zh/`, `/ja/`).
   - Identify base URL / canonical domain.

---

## Phase 2: Planning & Roadmap Artifact (SSOT)

Generate `SEO-OPTIMIZATION-ROADMAP.md` in the workspace root with prioritized deliverables:

### Priority Tier Classification:
- **P0 (Critical Crawling & Indexing Blockers)**:
  - Missing or duplicate `<title>` / `meta description`.
  - Internal broken links (404s) and redirect loops.
  - Faulty `robots.txt` blocking indexing or invalid `sitemap.xml`.
- **P1 (Ranking Factors & Social Distribution)**:
  - Open Graph (`og:title`, `og:description`, `og:image`, `og:url`, `og:type`).
  - Twitter Card tags (`twitter:card`, `twitter:site`, `twitter:creator`).
  - Canonical link tags (`rel="canonical"`) and Alternate Hreflang for multi-language.
- **P2 (Rich Results & Semantic Schema)**:
  - JSON-LD Structured Data (`WebSite`, `Organization`, `SoftwareApplication`, `Article`, `FAQPage`, `BreadcrumbList`).
  - Heading hierarchy normalization (single `<h1>` per page, sequential `<h2>`-`<h6>`).
- **P3 (Technical & Performance Polish)**:
  - Image alt attributes and modern image formats (WebP/AVIF).
  - Web vitals and semantic HTML tags (`<nav>`, `<header>`, `<main>`, `<article>`).

---

## Phase 3: Comprehensive Audit

1. **Static AST / Code Inspection**:
   - Audit metadata definitions across layout and page templates.
   - Verify that dynamic metadata functions properly handle fallback titles and descriptions.
2. **Dynamic DOM & Headless Inspection**:
   - Use `browser_navigate_tool` / `browser_snapshot_tool` or `web_fetch_tool` on local dev server or live URL.
   - Extract actual rendered `<head>` tags to ensure client-side hydration did not discard metadata.
3. **Link & Soft-404 Validation Probe**:
   - Run a non-destructive Python probe via `bash_code_execute_tool` to validate all internal hrefs and check HTTP status / DOM soft-404 indicators.

---

## Phase 4: Code Remediation

1. **Native Framework Metadata Implementation**:
   - In Next.js: Implement `export const metadata: Metadata` or `generateMetadata()`.
   - In Astro: Utilize `<SEO ... />` component or standard `<head>` frontmatter bindings.
   - In HTML/SPA: Inject standardized meta template tags.
2. **Dynamic Sitemap & Robots Generation**:
   - In Next.js: Create `app/sitemap.ts` and `app/robots.ts`.
   - In Astro: Configure `@astrojs/sitemap`.
3. **JSON-LD Schema Injection**:
   - Inject `<script type="application/ld+json">` with Schema.org compliant schema objects.
4. **Broken Link Repair**:
   - Correct typos in routing paths, replace outdated external URLs, and establish 301 redirects if needed.

---

## Phase 5: Verification & Quality Gate

1. **Deterministic Probe Execution**:
   - Re-run the link validator to guarantee **0 broken links**.
   - Verify JSON-LD syntax using standard schema validators.
2. **Cross-Language Consistency Check**:
   - Ensure alternate `hreflang` links point reciprocally across all supported languages.
3. **Deliverable Summary**:
   - Update `SEO-OPTIMIZATION-ROADMAP.md` marking completed items with `[x]`.
   - Output clear diff summary and actionable post-deployment suggestions (e.g. Google Search Console sitemap submission).
