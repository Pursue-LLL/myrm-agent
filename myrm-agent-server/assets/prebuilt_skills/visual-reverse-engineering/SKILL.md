---
name: visual-reverse-engineering
description: >-
  Visual reverse engineering protocol for UI screenshots, visual references, schematics, and design mockups.
  Enforces 4-step structural deduction: immutable datum spine anchor, topological hierarchy extraction,
  scale factor derivation, and non-orthogonal geometry projection.
version: 1.0.0
category: design
tags:
  - vision
  - topology
  - visual-engineering
  - datum-plane
  - reverse-engineering
allowed-tools: file_read_tool grep_tool glob_tool
contract:
  steps:
    - "Phase 1: Datum Plane & Spine Anchor — identify the immutable baseline, root container, or coordinate spine"
    - "Phase 2: Topological Graph Extraction — map containment hierarchy, adjacency ordering, and alignment graphs"
    - "Phase 3: Datum Scale Factor Derivation — infer relative scale factors and proportional spacing ratios from standard reference anchors"
    - "Phase 4: Non-Orthogonal Angle & Geometry Projection — resolve skew, perspective tilts, and non-orthogonal visual geometries"
    - "Phase 5: Parameterized Tokenized Synthesis — generate production-grade layout code without guessing raw pixel values"
  potential_traps:
    - description: "Guessing raw pixel values from sensory perception instead of calculating from datum anchors"
      mitigation: "Always derive numerical dimensions as multiples of a base grid anchored to a standard reference"
      severity: high
    - description: "Overlooking non-orthogonal angles, perspective distortion, or visual tilt in raster images"
      mitigation: "Decompose slanted vectors into trigonometric projections relative to the primary datum axis"
      severity: medium
    - description: "Flattening nested layout hierarchies into absolute positioning antipatterns"
      mitigation: "Strictly map topological parent-child containment and flex/grid flow before writing layout code"
      severity: high
  verification_steps:
    - step_id: datum_plane_verified
      description: "Primary datum plane and spine anchor are explicitly identified and logged"
      validation_method: "Explicit declaration of datum anchor in synthesis output"
      is_required: true
    - step_id: topology_and_scale_verified
      description: "Topological hierarchy and scale factors are verified against reference elements"
      validation_method: "Layout uses tokenized spacing and semantic parent-child containment"
      is_required: true
  success_criteria: "High-fidelity structural reconstruction with zero unanchored pixel guesses"
  estimated_duration_seconds: 1200
---

# Visual Reverse Engineering Protocol

## The Core Discipline

Never guess raw pixels in isolation. Always anchor every element to an immutable datum plane.

## 4-Step Reverse Engineering Protocol

### 1. Datum Plane & Spine Anchor
- Identify the foundational reference geometry:
  - Root viewport container or outer bounding card.
  - Primary vertical or horizontal symmetry axis.
  - Standard reference baseline (e.g., typography line-height, standard 36px/40px button).

### 2. Topological Graph Extraction
- Extract the structural containment and adjacency relationships:
  - Containment tree: identify parent flex/grid containers and nested child blocks.
  - Sibling flow: determine main-axis and cross-axis alignment.
  - Gap and margin distribution rules across layout nodes.

### 3. Datum Scale Factor Derivation
- Derive exact scale factors from known reference anchors:
  - Base spacing scale (4px / 8px Tailwind grid multiples).
  - Proportional sizing derived as ratio multipliers of the root datum dimensions.

### 4. Non-Orthogonal Angle & Geometry Projection
- Project slanted, rotated, or perspective-skewed visual elements:
  - Triangular decomposition for angles and diagonals.
  - CSS transform matrices or SVG polygon coordinates for non-orthogonal shapes.
