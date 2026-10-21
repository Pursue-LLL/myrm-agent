---
name: ui-design-restoration
description: >-
  Standard Operating Procedure for reverse engineering visual designs, extracting design systems,
  color palettes, typography scale, component layouts, and reconstructing code from screenshots.
  UI 设计图与截图逆向还原 SOP：主色提炼、组件布局重构与前端代码无损还原。
version: 1.0.0
category: engineering
tags:
  - ui
  - design-system
  - reverse-engineering
  - vision
  - tailwind
  - react
  - 设计图还原
  - 前端还原
allowed-tools: browser_navigate_tool bash_code_execute_tool web_search_tool file_read_tool file_write_tool file_edit_tool
contract:
  steps:
    - "Phase 1: Visual Decomposition — analyze canvas layout, grid system, and responsive breakpoints"
    - "Phase 2: Design Token Extraction — extract dominant brand colors, background tints, and font scale"
    - "Phase 3: Component Hierarchy Mapping — identify atoms (buttons, badges), molecules (inputs, cards), and organisms"
    - "Phase 4: Code Generation — implement responsive React + Tailwind CSS code matching visual hierarchy"
    - "Phase 5: Visual Diff & Refinement — verify alignment, padding, border radius, and contrast fidelity"
  potential_traps:
    - description: "Hallucinating arbitrary hex colors instead of extracting precise values"
      mitigation: "Use Python PIL in sandbox or exact color picking script to sample pixel hex values directly"
      severity: high
    - description: "Hardcoding pixel widths causing responsive layout breakages"
      mitigation: "Adopt fluid Tailwind container classes (w-full, max-w-*, flex-1, grid-cols-*) instead of fixed widths"
      severity: high
    - description: "Blurry text transcription from extreme vertical long screenshots"
      mitigation: "Rely on slice_long_image_if_needed tiled sections to inspect individual headers and badges cleanly"
      severity: medium
  verification_steps:
    - step_id: color_accuracy
      description: "Ensure primary, neutral, and accent colors match source image within tolerance"
      validation_method: "Cross-check hex codes against extracted palette"
      is_required: true
    - step_id: responsive_layout
      description: "Verify layout behaves correctly on mobile and desktop viewports"
      validation_method: "Inspect flex/grid configurations"
      is_required: true
  success_criteria: "Pixel-accurate, semantic, and responsive component code generated from visual reference"
  estimated_duration_seconds: 300
---

# UI Design Restoration SOP

## Bash execution contract

- Use `bash_code_execute_tool` only when shell execution is necessary for color sampling or layout validation.
- Every bash invocation must include a concrete, user-relevant reason.
- Prefer non-destructive commands and keep all operations confined to workspace files for this task.
- Do not run unrelated background processes or broad system-level commands.

This skill guides the Agent in faithfully reconstructing high-fidelity UI components and complete application screens from visual design assets or screenshots.

## Phase 1: Visual Decomposition & Grid Analysis
1. Inspect the overall page structure: Header, Hero, Main Content, Sidebar, Footer.
2. Determine layout rhythm: standard 8pt/4pt spacing grid, card padding (e.g. `p-6`), and border radius (e.g. `rounded-xl`).
3. For long page screenshots, inspect each sliced section sequentially to capture fine details without distortion.

## Phase 2: Design Token Extraction
When analyzing screenshots, run a lightweight sandbox script if needed to extract the dominant color palette:
```python
from PIL import Image
from collections import Counter

img = Image.open("screenshot.png")
colors = Counter(img.convert("RGB").getdata()).most_common(5)
for count, col in colors:
    print(f"#{col[0]:02x}{col[1]:02x}{col[2]:02x}: {count}")
```
Translate discovered colors into semantic Tailwind classes (e.g. `bg-slate-900`, `text-indigo-400`).

## Phase 3: Semantic Component Rebuilding
- Avoid div-soup: use `<main>`, `<section>`, `<header>`, `<article>`, `<button>`.
- Typography: map font weights and sizes to standard scales (`text-xs font-medium`, `text-2xl font-bold`).
- Micro-interactions: incorporate hover states (`hover:bg-primary/90 transition-colors`), focus rings, and active states.

## Phase 4: Self-Audit Checklist
- [ ] Are all icons mapped to standard Lucid/Heroicon equivalents?
- [ ] Are mobile vs desktop responsive variants implemented (`hidden md:flex`)?
- [ ] Is contrast compliant with WCAG AA guidelines?
