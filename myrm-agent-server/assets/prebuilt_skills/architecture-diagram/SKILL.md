---
name: architecture-diagram
description: >-
  Generate professional dark-themed SVG architecture diagrams as standalone HTML
  files. No external tools or API keys required — pure HTML+SVG output that opens
  in any browser.
version: 1.0.0
category: creative
tags:
  - architecture
  - diagrams
  - SVG
  - visualization
  - infrastructure
allowed-tools: file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Understand — gather system components, connections, and technologies"
    - "Phase 2: Layout — determine component grouping, hierarchy, and flow direction"
    - "Phase 3: Generate — create the HTML file with inline SVG following the design system"
    - "Phase 4: Deliver — save the file and provide opening instructions"
  potential_traps:
    - description: "Overcrowding the diagram with too many components"
      mitigation: "Group related components into boundary boxes; limit to 15-20 visible elements"
      severity: medium
    - description: "Arrow z-order issues causing arrows to show through semi-transparent fills"
      mitigation: "Draw arrows early in SVG (after grid), use double-rect masking for components"
      severity: low
  verification_steps:
    - step_id: single_file
      description: "Output is a single self-contained HTML file"
      validation_method: "File opens correctly in any browser with no external dependencies"
      is_required: true
  success_criteria: "Professional-quality architecture diagram that clearly communicates system structure"
  estimated_duration_seconds: 600
---

# Architecture Diagram

Generate professional, dark-themed technical architecture diagrams as standalone HTML files with inline SVG graphics. No external tools, no API keys — just write the HTML file.

## Scope

**Best suited for:**
- Software system architecture (frontend / backend / database layers)
- Cloud infrastructure (VPC, regions, subnets, managed services)
- Microservice topology and service mesh
- Database + API map, deployment diagrams

## Workflow

1. **Understand** — Ask the user about their system components, connections, and technologies
2. **Layout** — Determine grouping, hierarchy, and flow direction
3. **Generate** — Create the HTML file following the design system below
4. **Deliver** — Save with `file_write_tool` and suggest opening in browser

## Design System

### Color Palette

| Component Type | Fill (rgba) | Stroke (Hex) |
|:---|:---|:---|
| **Frontend** | `rgba(8, 51, 68, 0.4)` | `#22d3ee` (cyan) |
| **Backend** | `rgba(6, 78, 59, 0.4)` | `#34d399` (emerald) |
| **Database** | `rgba(76, 29, 149, 0.4)` | `#a78bfa` (violet) |
| **Cloud/Infra** | `rgba(120, 53, 15, 0.3)` | `#fbbf24` (amber) |
| **Security** | `rgba(136, 19, 55, 0.4)` | `#fb7185` (rose) |
| **Message Bus** | `rgba(251, 146, 60, 0.3)` | `#fb923c` (orange) |
| **External** | `rgba(30, 41, 59, 0.5)` | `#94a3b8` (slate) |

### Typography & Background

- **Font:** Monospace (system default or JetBrains Mono via Google Fonts)
- **Background:** `#020617` with subtle 40px grid pattern
- **Text:** White for labels, muted for annotations

### Layout Rules

- **Components:** Rounded rectangles (`rx="6"`) with 1.5px strokes
- **Arrows:** Drawn early in SVG so they render behind component boxes
- **Security groups:** Dashed borders in rose color
- **Minimum gap:** 40px between components vertically
- **Legend:** Placed outside all boundary boxes, at least 20px below lowest element

## Output Requirements

- **Single file:** One self-contained `.html` file
- **No external dependencies:** All CSS and SVG inline (except optional Google Fonts)
- **No JavaScript:** Pure CSS for any animations
- **Cross-browser:** Must render in any modern browser

## Document Structure

```html
<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>{System Name} Architecture</title>
  <style>/* Dark theme CSS */</style>
</head>
<body>
  <!-- Header with title -->
  <!-- Main SVG diagram -->
  <!-- Summary cards (optional) -->
  <!-- Footer -->
</body>
</html>
```
