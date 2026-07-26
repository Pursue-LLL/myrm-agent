---
name: infographic
description: >-
  Generate professional infographics with 21 layouts × 21 styles (441 combinations).
  Supports both image generation and interactive HTML+CSS output.
  信息图生成：21种布局×21种风格，支持图片和HTML两种产出模式。
version: 1.0.0
category: creative
tags:
  - infographic
  - visual-summary
  - creative
  - image-generation
  - 信息图
  - 可视化
  - 高密度信息大图
  - data-visualization
license: MIT
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool image_tool ask_question_tool browser_navigate_tool
---

# Infographic Generator

Two dimensions: **layout** (information structure) × **style** (visual aesthetics). Freely combine any layout with any style.

## When to Use

Trigger this skill when the user asks to create an infographic, visual summary, information graphic, or uses terms like "信息图", "可视化", or "高密度信息大图". The user provides content (text, file path, URL, or topic) and optionally specifies layout, style, aspect ratio, or language.

## Bash execution contract

- Use `bash_code_execute_tool` only for deterministic local operations that directly support this skill workflow.
- Every bash tool call must include a specific, user-facing reason in plain language.
- Prefer read/transform/generate steps; avoid destructive shell operations.
- Keep commands scoped to workspace files created or consumed by the current infographic task.

## Options

| Option | Values |
|--------|--------|
| Layout | 21 options (see Layout Gallery), default: bento-grid |
| Style | 21 options (see Style Gallery), default: craft-handmade |
| Aspect | Named: landscape (16:9), portrait (9:16), square (1:1). Custom: any W:H ratio |
| Language | en, zh, ja, etc. |
| Output | `image` (default) or `html` (interactive, editable) |

## Layout Gallery

| Layout | Best For |
|--------|----------|
| `linear-progression` | Timelines, processes, tutorials |
| `binary-comparison` | A vs B, before-after, pros-cons |
| `comparison-matrix` | Multi-factor comparisons |
| `hierarchical-layers` | Pyramids, priority levels |
| `tree-branching` | Categories, taxonomies |
| `hub-spoke` | Central concept with related items |
| `structural-breakdown` | Exploded views, cross-sections |
| `bento-grid` | Multiple topics, overview (default) |
| `iceberg` | Surface vs hidden aspects |
| `bridge` | Problem-solution |
| `funnel` | Conversion, filtering |
| `isometric-map` | Spatial relationships |
| `dashboard` | Metrics, KPIs |
| `periodic-table` | Categorized collections |
| `comic-strip` | Narratives, sequences |
| `story-mountain` | Plot structure, tension arcs |
| `jigsaw` | Interconnected parts |
| `venn-diagram` | Overlapping concepts |
| `winding-roadmap` | Journey, milestones |
| `circular-flow` | Cycles, recurring processes |
| `dense-modules` | High-density modules, data-rich guides |

Full definitions: `references/layouts/<layout>.md`

## Style Gallery

| Style | Description |
|-------|-------------|
| `craft-handmade` | Hand-drawn, paper craft (default) |
| `claymation` | 3D clay figures, stop-motion |
| `kawaii` | Japanese cute, pastels |
| `storybook-watercolor` | Soft painted, whimsical |
| `chalkboard` | Chalk on black board |
| `cyberpunk-neon` | Neon glow, futuristic |
| `bold-graphic` | Comic style, halftone |
| `aged-academia` | Vintage science, sepia |
| `corporate-memphis` | Flat vector, vibrant |
| `technical-schematic` | Blueprint, engineering |
| `origami` | Folded paper, geometric |
| `pixel-art` | Retro 8-bit |
| `ui-wireframe` | Grayscale interface mockup |
| `subway-map` | Transit diagram |
| `ikea-manual` | Minimal line art |
| `knolling` | Organized flat-lay |
| `lego-brick` | Toy brick construction |
| `pop-laboratory` | Blueprint grid, coordinate markers, lab precision |
| `morandi-journal` | Hand-drawn doodle, warm Morandi tones |
| `retro-pop-grid` | 1970s retro pop art, Swiss grid, thick outlines |
| `hand-drawn-edu` | Macaron pastels, hand-drawn wobble, stick figures |

Full definitions: `references/styles/<style>.md`

## Recommended Combinations

| Content Type | Layout + Style |
|--------------|----------------|
| Timeline/History | `linear-progression` + `craft-handmade` |
| Step-by-step | `linear-progression` + `ikea-manual` |
| A vs B | `binary-comparison` + `corporate-memphis` |
| Hierarchy | `hierarchical-layers` + `craft-handmade` |
| Overlap | `venn-diagram` + `craft-handmade` |
| Conversion | `funnel` + `corporate-memphis` |
| Cycles | `circular-flow` + `craft-handmade` |
| Technical | `structural-breakdown` + `technical-schematic` |
| Metrics | `dashboard` + `corporate-memphis` |
| Educational | `bento-grid` + `chalkboard` |
| Journey | `winding-roadmap` + `storybook-watercolor` |
| Categories | `periodic-table` + `bold-graphic` |
| Product Guide | `dense-modules` + `morandi-journal` |
| Technical Guide | `dense-modules` + `pop-laboratory` |
| Trendy Guide | `dense-modules` + `retro-pop-grid` |
| Educational Diagram | `hub-spoke` + `hand-drawn-edu` |

Default: `bento-grid` + `craft-handmade`

## Keyword Shortcuts

| User Keyword | Layout | Recommended Styles | Default Aspect |
|--------------|--------|--------------------|----------------|
| 高密度信息大图 / high-density-info | `dense-modules` | `morandi-journal`, `pop-laboratory`, `retro-pop-grid` | portrait |
| 信息图 / infographic | `bento-grid` | `craft-handmade` | landscape |

## Core Principles

- Preserve source data faithfully — no summarization or rephrasing
- Strip any credentials, API keys, tokens, or secrets before including in outputs
- Define learning objectives before structuring content
- Structure for visual communication (headlines, labels, visual elements)

## Workflow

### Step 1: Analyze Content

**Load references**: Read `references/analysis-framework.md` from this skill.

1. Save source content to workspace
2. Analyze: topic, data type, complexity, tone, audience
3. Detect source language and user language
4. Extract design instructions from user input
5. Save analysis

See `references/analysis-framework.md` for detailed format.

### Step 2: Generate Structured Content

Transform content into infographic structure:
1. Title and learning objectives
2. Sections with: key concept, content (verbatim), visual element, text labels
3. Data points (all statistics/quotes copied exactly)
4. Design instructions from user

See `references/structured-content-template.md` for detailed format.

### Step 3: Recommend Combinations

**Check Keyword Shortcuts first**: If user input matches a keyword from the table, auto-select the associated layout.

Otherwise, recommend 3-5 layout×style combinations based on data structure, content tone, and audience.

### Step 4: Confirm Options

Use the `ask_question_tool` to confirm options with the user:
- **Q1**: Present 3+ layout×style combos with rationale
- **Q2**: Ask for aspect ratio preference
- **Q3**: Ask output format preference (image or HTML)
- **Q4** (if needed): Ask language for text content

### Step 5: Generate Prompt

**Load references**: Read the selected layout from `references/layouts/<layout>.md` and style from `references/styles/<style>.md`.

Combine: layout definition + style definition + base template from `references/base-prompt.md` + structured content.

### Step 6: Generate Output

**Image mode** (default): Use the `image_tool` with the assembled prompt.
- Map aspect ratio: `16:9` → landscape, `9:16` → portrait, `1:1` → square

**HTML mode**: Generate a self-contained HTML artifact with:
- CSS that implements the selected style's color palette, typography, and visual elements
- Layout structure matching the selected layout pattern
- Responsive design with appropriate breakpoints
- All text content embedded inline
- SVG icons and decorative elements as needed
- **Verify rendering** (when browser available): serve locally and use `browser_navigate_tool` with a `verify_goal` describing the expected layout and style — the tool runs a 3-layer visual check automatically. Fix any rendering issues before delivery.

### Step 7: Output Summary

Report: topic, layout, style, aspect, language, output format, and result.

## References

- `references/analysis-framework.md` — Analysis methodology
- `references/structured-content-template.md` — Content format
- `references/base-prompt.md` — Prompt template
- `references/layouts/<layout>.md` — 21 layout definitions
- `references/styles/<style>.md` — 21 style definitions

## Pitfalls

1. **Data integrity is paramount** — never summarize or alter source statistics
2. **Strip secrets** — always scan for API keys or credentials before output
3. **One concept per section** — overloading reduces readability
4. **Style consistency** — apply the chosen style uniformly across the entire output
5. **image_generation aspect ratios** — only supports landscape, portrait, square
