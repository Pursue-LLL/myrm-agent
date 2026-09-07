---
name: visual-reverse-engineering
description: >-
  Standard Operating Procedure for reverse engineering structural dimensions, topological adjacency,
  and scale from visual references (drawings, photos, diagrams, sketches).
  基于视觉底图的绝对基准面锚定、拓扑轴线提取与物理比例逆向工程规程。
version: 1.0.0
category: engineering
tags:
  - vision
  - reverse-engineering
  - topology
  - datum-plane
  - diagrams
  - architecture
  - 视觉逆向
  - 拓扑分析
allowed-tools: bash_code_execute_tool file_read_tool file_write_tool file_edit_tool
contract:
  steps:
    - "Phase 1: Datum Plane & Spine Anchoring — anchor to immutable base or central spine first"
    - "Phase 2: Topological Graph Extraction — extract containment, hierarchy, and connection paths before numbers"
    - "Phase 3: Datum Scale Factor Derivation — derive scale from known standard objects instead of guessing pixels"
    - "Phase 4: Non-Orthogonal Angle & Geometry Projection — resolve angled components via triangle projection"
    - "Phase 5: Parameterized Reconstruction — emit verified code, SVG, or structural specifications"
  potential_traps:
    - description: "Guessing arbitrary pixel distances without establishing reference scale"
      mitigation: "Always identify a known element (standard font height, button height, grid pitch) as scale anchor"
      severity: high
    - description: "Inverting or misaligning parent-child hierarchical containment"
      mitigation: "Map topological adjacency tree before generating coordinate layouts"
      severity: high
    - description: "Distortion from perspective tilt or non-orthogonal angles"
      mitigation: "Use geometric projection formulas or sandbox Python scripts to calculate true orthogonal dimensions"
      severity: medium
  verification_steps:
    - step_id: datum_anchor_check
      description: "Verify that all components are measured relative to the established datum spine"
      validation_method: "Confirm root coordinate system consistency"
      is_required: true
    - step_id: topology_integrity
      description: "Ensure no broken adjacency links or inverted parent-child relationships"
      validation_method: "Audit tree structure against visual input"
      is_required: true
  success_criteria: "Strictly proportional, structurally sound, and topologically verified reconstruction from visual input"
  estimated_duration_seconds: 180
---

# Visual Datum and Topology Reverse Engineering SOP

## Bash Execution Contract

- Use `bash_code_execute_tool` only when computational geometry, image slicing, or matrix projection is required.
- Execute calculations within local workspace sandbox.
- Maintain zero mutation of source reference assets.

## Core Principles (The 4-Step Reverse Engineering Paradigm)

When reconstructing code, Mermaid diagrams, CAD parameters, or structural layouts from drawings, sketches, or photos:

### 1. Datum Plane & Spine Anchor (绝对基准面锚定)
- Never start by measuring random floating elements.
- **Identify the immutable ground plane or central spine**:
  - For UI / Web: Viewport canvas root, top header bar, or primary 12-column grid container.
  - For Diagrams / Flowcharts: Start node / root coordinator / main vertical swimlane spine.
  - For Physical / Architectural drawings: Ground elevation line, load-bearing slab, or centerline column grid.
- All subsequent coordinates $(x, y, z)$ must be expressed relative to this immutable datum.

### 2. Topological Graph Extraction (拓扑包含与邻接提取)
- Extract the qualitative structure **before** assigning numerical values:
  - **Containment (父子包含)**: Node A contains [B, C].
  - **Adjacency (同级邻接)**: Node B is positioned immediately to the left of Node C with a shared boundary.
  - **Connection Paths (连接流向)**: Edge from Node B to Node D with directional arrow.
- Constructing the topological graph first ensures that layout errors cannot break logical connectivity.

### 3. Datum Scale Factor Derivation (已知基准反求比例尺)
- **Do NOT guess pixel dimensions raw.**
- Find an element with a known or standardized physical dimension:
  - Text typography baseline (e.g. standard body font $\approx 14\text{px} \sim 16\text{px}$).
  - Standard touch target height ($\approx 40\text{px} \sim 48\text{px}$).
  - Stated dimension callouts or scale bars in technical drawings.
- Calculate the unified scale ratio:
  $$\text{Scale Factor } S = \frac{\text{Known Dimension (Units)}}{\text{Measured Pixel Span}}$$
- Multiply all measured pixel spans by $S$ to obtain clean, proportional, normalized numbers.

### 4. Non-Orthogonal Angle & Geometry Projection (非正交倾角消解)
- If components are slanted, skewed, or shown in perspective:
  - Isolate the feature into right-angle projected triangles:
    $$L_{\text{true}} = \sqrt{\Delta x^2 + \Delta y^2}$$
    $$\theta = \arctan\left(\frac{\Delta y}{\Delta x}\right)$$
  - Never eyeball angles; express them in explicit parametric rotation or vector offsets.

## Execution Checklist

- [ ] Immutable datum plane or spine identified and declared.
- [ ] Topological hierarchy mapped without broken edges.
- [ ] Reference scale factor $S$ derived from standard anchor.
- [ ] Non-orthogonal components projected and verified.
- [ ] Reconstructed output (React/Tailwind, Mermaid, Canvas, JSON) compiles and matches visual ground truth.
