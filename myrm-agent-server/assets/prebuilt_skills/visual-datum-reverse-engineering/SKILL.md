---
name: visual-datum-reverse-engineering
description: >-
  Reverse engineering discipline for visual references, sketches, blueprints, and UI screenshots.
  Enforces 4-step structural deduction: immutable datum spine anchor → topological graph extraction
  → relative pitch/scale derivation from known references → parameterized generation without guessing pixels.
version: 1.0.0
category: design
tags:
  - visual-engineering
  - datum-plane
  - reverse-engineering
  - topology
  - multimodality
  - design-to-code
allowed-tools: bash_code_execute_tool file_read_tool grep_tool glob_tool
contract:
  steps:
    - "Phase 1: Datum Plane & Spine Anchor — locate the ground plane, primary axis, or bounding container"
    - "Phase 2: Topological Graph Extraction — map containment, adjacency, and alignment hierarchy"
    - "Phase 3: Scale & Pitch Derivation — infer relative proportions from standard reference elements"
    - "Phase 4: Parameterized Synthesis — generate code/diagrams using computed tokens and grid systems"
  potential_traps:
    - description: "Guessing absolute pixel values from visual perception instead of anchoring to references"
      mitigation: "Always derive numerical dimensions from a known datum anchor (e.g., standard text/button height)"
      severity: high
    - description: "Neglecting non-orthogonal angles or visual perspective distortion"
      mitigation: "Use projected triangular decompositions to isolate perspective and skew"
      severity: medium
  verification_steps:
    - step_id: datum_anchor_identified
      description: "Primary datum plane or spine axis is explicitly stated before generating code"
      validation_method: "Response contains explicit datum anchor declaration"
      is_required: true
    - step_id: topology_mapped
      description: "Containment and adjacency relationships are clearly established"
      validation_method: "Hierarchy follows standard layout/AST composition"
      is_required: true
  success_criteria: "High-fidelity reconstruction adhering to structural proportions with zero pixel-guessing artifacts"
  estimated_duration_seconds: 1200
---

# Visual Datum & Topology Reverse Engineering

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## The Iron Law of Visual Reverse Engineering

```
NEVER GUESS RAW PIXELS — ANCHOR TO AN IMMUTABLE DATUM FIRST
```

When translating UI screenshots, architectural drawings, hand-drawn wireframes, or flowcharts into code/Mermaid/Canvas:
1. Do not estimate visual sizes in isolation.
2. Establish a reference grid based on standard known elements (base font, standard icon bounding box, or container width).
3. Compute all child dimensions as fractional multipliers of the datum spine.

## 4-Step Reverse Engineering Protocol

### Step 1: Datum Spine Anchor (基准面与中轴锚定)
- Identify the immutable baseline:
  - **For UI / Web**: Viewport width, header/navbar fixed height, or root layout container.
  - **For Diagrams / Workflows**: Entry trigger node and terminal sink node.
  - **For Engineering / Drawings**: Ground baseline, primary load-bearing spine, or center symmetry axis.

### Step 2: Topological Graph Extraction (拓扑层次提取)
- Map relationships before assigning values:
  - **Containment**: Which elements nest inside which containers (Flex/Grid/Box).
  - **Adjacency**: Horizontal vs Vertical flow (row/col direction, sibling ordering).
  - **Alignment**: Center, stretch, start, or space-between alignments.

### Step 3: Scale & Pitch Derivation (模数比例反推)
- Derive scale from known reference anchors:
  - Standard body text = 1rem / 16px.
  - Standard button height = 36px / 40px / 44px.
  - Base spacing scale = 4px / 8px multiples (Tailwind grid).
  - Derive margins, padding, and gaps relative to the base spacing scale.

### Step 4: Parameterized Synthesis (参数化高保真生成)
- Generate clean, tokenized layout code:
  - Use relative units (`rem`, `%`, `flex`, `grid`, `gap-X`).
  - Isolate non-orthogonal angles or irregular shapes using CSS transforms or SVG vector paths.
  - Assert that all sibling elements maintain consistent visual cadence.
