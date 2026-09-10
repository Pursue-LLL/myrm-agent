---
name: brand-vi-guidelines
description: "Extract, synthesize, and enforce consistent corporate brand Visual Identity (VI) tokens, typography scales, color palettes, and presentation design constraints from collaborative design discussions."
version: "1.0.0"
category: "design"
tags:
  - brand-vi
  - design-system
  - guidelines
  - design-tokens
  - presentation-rules
allowed-tools:
  - file_write_tool
  - file_read_tool
---

# Brand VI Guidelines & Design Constraints (品牌 VI 规范与视觉约束技能)

## Overview

A dedicated skill for crystallizing collaborative design discussions, brainstorming sessions, and brand identity reviews into a structured, executable **Brand Visual Identity (VI) Guidelines and Constraint Pack (`brand-vi.yaml` / `brand-vi.md`)**.

It ensures that all subsequent agent deliverables (slides, web pages, posters, PDF briefs) strictly honor the extracted brand tokens and presentation rules.

---

## 5 Core VI Pillars (五大视觉识别基石)

When summarizing design sessions into a brand skill pack, extract and define these 5 core pillars:

```
1. Color Palette & Accessibility Matrix (调色板与无障碍对比度)
   ├── Primary, Secondary, Background, Surface, Border, Text Primary/Muted
   └── WCAG AA Contrast Compliance ratios
2. Typography Hierarchy (排版字体层级)
   ├── Heading font-family, Body font-family, Monospace font-family
   └── Font-size scale (h1: 32-40px, h2: 24-28px, body: 14-16px, caption: 12px)
3. Grid & Spacing System (网格与留白系统)
   ├── 4px / 8px incremental spacing scale
   └── 16:9 presentation slide safe zones (min 48px padding)
4. Component Elevation & Border Radius (圆角与层级质感)
   ├── Default border-radius (e.g., 8px, 12px, full-pill)
   └── Shadow elevation tiers (subtle, card, modal)
5. Anti-Patterns & Negative Rules (负向约束与反设计禁令)
   ├── Prohibited color combinations
   └── Anti-wall-of-text & forbidden native emoji rules
```

---

## Structured Output Contract (`brand-vi.yaml`)

Every summarized brand session should produce a machine-readable token definition:

```yaml
brand_name: "Acme Corp"
version: "1.0.0"

tokens:
  colors:
    primary: "#2563EB"
    primary_hover: "#1D4ED8"
    background: "#0F172A"
    card: "#1E293B"
    text_primary: "#F8FAFC"
    text_muted: "#94A3B8"
    border: "rgba(255, 255, 255, 0.1)"
    danger: "#EF4444"
    success: "#10B981"
  typography:
    heading_font: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    body_font: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"
    weights:
      regular: 400
      medium: 500
      bold: 700
  geometry:
    radius_sm: "4px"
    radius_md: "8px"
    radius_lg: "12px"
    radius_pill: "9999px"

rules:
  - "Never use unstyled native platform emojis on official company interfaces or decks."
  - "Maintain a minimum contrast ratio of 4.5:1 for all readable body text."
  - "All presentation slides must maintain 16:9 widescreen aspect ratio with >= 48px outer margins."
  - "No slide may exceed 4 bullet points or 60 total words (anti-wall-of-text rule)."
```

---

## Downstream Deliverables Enforcement

When generating HTML, PPTX (via python-pptx), or React components under an active brand skill pack:
1. Load `tokens.colors` and bind them directly to CSS variables or presentation shape fills.
2. Verify all title/body text against `typography` rules.
3. Automatically block deliverables violating the `rules` section.
