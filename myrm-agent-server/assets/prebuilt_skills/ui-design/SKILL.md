---
name: ui-design
description: >-
  Craft distinctive, production-grade frontend interfaces with exceptional visual quality.
  Covers bold typography, cohesive color systems, motion design, spatial composition,
  and rich visual details. Produces memorable UI that avoids generic AI aesthetics.
version: 1.0.0
category: design
tags:
  - ui-design
  - visual-design
  - typography
  - aesthetics
  - frontend
  - tailwind
  - motion
  - creative
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool grep_tool
contract:
  steps:
    - "Phase 1: Design Intent — understand purpose, audience, and commit to a bold aesthetic direction"
    - "Phase 2: Visual System — establish typography, color palette, spatial rhythm, and motion language"
    - "Phase 3: Implement — build production-grade code with meticulous aesthetic execution"
    - "Phase 4: Refine — audit visual cohesion, motion polish, responsive elegance, and uniqueness"
  potential_traps:
    - description: "Falling into generic AI aesthetics — Inter font, purple gradients, predictable card layouts"
      mitigation: "Every design must have a clear conceptual direction; verify font choices are distinctive and contextually appropriate"
      severity: critical
    - description: "Over-animating with scattered micro-interactions instead of orchestrated motion"
      mitigation: "Focus on 2-3 high-impact motion moments (page load stagger, hover reveals, scroll triggers) rather than animating everything"
      severity: high
    - description: "Sacrificing usability for visual flair — unreadable text, confusing navigation"
      mitigation: "Maintain WCAG AA contrast ratios; test readability at all breakpoints; keep navigation patterns intuitive"
      severity: high
    - description: "Converging on the same aesthetic across different projects"
      mitigation: "Vary themes (light/dark), font pairings, layout approaches, and color schemes for each new project"
      severity: medium
  verification_steps:
    - step_id: aesthetic_direction_set
      description: "A clear, intentional aesthetic direction is chosen and articulated before coding"
      validation_method: "Design intent statement exists with tone, differentiation, and font/color choices"
      is_required: true
    - step_id: typography_distinctive
      description: "Typography uses distinctive, contextually appropriate fonts — not generic defaults"
      validation_method: "Verify font choices are not Inter, Roboto, Arial, or system defaults"
      is_required: true
    - step_id: visual_cohesion_verified
      description: "Color system, spacing rhythm, and visual details form a cohesive whole"
      validation_method: "CSS variables defined for colors; consistent spacing scale; backgrounds have depth"
      is_required: true
    - step_id: motion_polished
      description: "Motion design enhances the experience with purposeful, orchestrated animations"
      validation_method: "Key transitions use staggered timing; hover states are refined; no jarring movements"
      is_required: false
  success_criteria: "A visually striking, production-ready interface with a clear aesthetic identity that feels genuinely designed, not AI-generated"
  estimated_duration_seconds: 2400
---

# UI Design

## Overview

Great UI is not just functional — it's memorable. This skill transforms frontend code from generic templates into distinctive, polished interfaces with genuine design character. The goal is production-grade code that looks and feels like it was crafted by a senior designer, not assembled by an algorithm.

**Core principle:** Every interface deserves a point of view. Bold maximalism and refined minimalism both work — the enemy is mediocrity and sameness.

## Phase 1: Design Intent

Before writing any code, establish a clear creative direction:

1. **Purpose** — What problem does this interface solve? Who is the audience?
2. **Tone** — Commit to a specific aesthetic direction:
   - Brutally minimal / Maximalist chaos / Retro-futuristic / Organic & natural
   - Luxury & refined / Playful & toy-like / Editorial & magazine / Brutalist & raw
   - Art deco & geometric / Soft & pastel / Industrial & utilitarian / Neo-morphic
   - Or any other intentional direction — the key is **commitment**, not intensity
3. **Differentiation** — What makes this UNFORGETTABLE? What's the one visual element someone will remember?
4. **Constraints** — Framework, performance budgets, accessibility requirements

### Design Intent Statement Template

```
Aesthetic: [chosen direction]
Signature element: [the unforgettable detail]
Font pairing: [display font] + [body font]
Color strategy: [dominant/accent approach]
Motion philosophy: [restrained elegance / orchestrated drama / etc.]
```

## Phase 2: Visual System

### Typography

Typography is the foundation of visual identity. Choose fonts that are **beautiful, unique, and contextually appropriate**.

**NEVER use these overused defaults:**
- Inter, Roboto, Arial, Helvetica, system-ui, sans-serif (as primary)
- Space Grotesk (overused in AI-generated designs)

**Instead, explore distinctive alternatives:**

| Category | Examples |
|----------|---------|
| Modern geometric sans | Plus Jakarta Sans, Outfit, General Sans, Cabinet Grotesk, Switzer |
| Elegant serif | Playfair Display, Cormorant, Fraunces, Libre Caslon, Source Serif 4 |
| Technical mono | JetBrains Mono, Berkeley Mono, IBM Plex Mono, Fira Code |
| Expressive display | Clash Display, Satoshi, Darker Grotesque, Instrument Sans |
| Humanist warmth | Source Sans 3, DM Sans, Nunito Sans, Lexend |

**Pairing strategy:** Combine a distinctive display font with a refined body font. Contrast in weight, width, or style creates visual interest.

### Color & Theme

- **Commit to a cohesive palette** — Use CSS variables for consistency
- **Dominant + accent** — One strong color with sharp accents outperforms timid, evenly-distributed palettes
- **Dark themes need depth** — Not just white-on-black; use subtle gradients, elevated surfaces, and muted accents
- **Light themes need contrast** — Avoid the washed-out look; use bold typography and strategic color blocks

### Spatial Composition

Break free from predictable grid layouts:

- **Asymmetry** — Intentional imbalance creates visual energy
- **Overlap** — Elements crossing boundaries add depth and dynamism
- **Generous negative space** — Or controlled density, depending on the aesthetic
- **Grid-breaking elements** — Let hero sections, images, or CTAs break the grid deliberately
- **Diagonal flow** — Guide the eye along unexpected paths

### Motion Language

- **Orchestrated > scattered** — One well-timed page load with staggered reveals creates more delight than random micro-interactions
- **CSS-first** — Use CSS transitions and animations for performance; reach for Motion/Framer only when CSS can't express the intent
- **High-impact moments** — Focus on: page load entrance, scroll-triggered reveals, hover state transformations
- **Timing is everything** — Use `animation-delay` for staggered sequences; ease curves should match the aesthetic (snappy for modern, gentle for organic)

## Phase 3: Implement

### Visual Details Checklist

These details separate "generated" from "designed":

- [ ] **Backgrounds have depth** — Gradient meshes, noise textures, geometric patterns, layered transparencies, or atmospheric effects — never just solid colors
- [ ] **Shadows are intentional** — Realistic multi-layer shadows for elevation, or dramatic shadows for contrast
- [ ] **Borders are refined** — Subtle borders with custom colors, or bold decorative borders that serve the aesthetic
- [ ] **Icons are cohesive** — Consistent icon style (line weight, corner radius) from a single icon set
- [ ] **Images are treated** — Rounded corners, overlays, masks, or frames that integrate images into the design system
- [ ] **Hover states surprise** — Color shifts, scale transforms, shadow elevations, or reveal animations
- [ ] **Empty states are designed** — Illustrations or thoughtful messaging for zero-data states

### Tailwind Best Practices for Design Quality

```tsx
{/* Layered background with depth */}
<div className="relative bg-gradient-to-br from-stone-950 via-stone-900 to-stone-950">
  <div className="absolute inset-0 bg-[radial-gradient(circle_at_30%_20%,rgba(120,80,200,0.15),transparent_50%)]" />
  <div className="relative z-10">...</div>
</div>

{/* Staggered entrance animation */}
<div className="animate-in fade-in slide-in-from-bottom-4 duration-700"
     style={{ animationDelay: '200ms' }}>

{/* Refined hover with multiple properties */}
<button className="group relative overflow-hidden rounded-xl bg-white px-6 py-3
  shadow-sm transition-all duration-300
  hover:shadow-xl hover:-translate-y-0.5">
  <span className="relative z-10 transition-colors group-hover:text-indigo-600">
    Get Started
  </span>
  <div className="absolute inset-0 -translate-x-full bg-indigo-50
    transition-transform duration-500 group-hover:translate-x-0" />
</button>
```

### Implementation Standards

| Rule | Rationale |
|------|-----------|
| CSS variables for all design tokens | Theme consistency and easy dark mode |
| Google Fonts via `@import` or `<link>` | Distinctive typography without self-hosting |
| `backdrop-blur` and `bg-opacity` for glass effects | Modern depth without heavy assets |
| `mix-blend-mode` for creative overlays | Unique visual textures |
| Gradient borders via background-clip trick | Elevated visual refinement |
| Custom `@keyframes` for unique animations | Personality in motion |

## Phase 4: Refine

### Visual Cohesion Audit

- [ ] **Font consistency** — Display font used only for headings; body font for all reading text; no surprise third fonts
- [ ] **Color discipline** — Every color traces back to the defined palette; no random hex values
- [ ] **Spacing rhythm** — Consistent spacing scale (4px/8px/16px/24px/32px/48px/64px); no arbitrary gaps
- [ ] **Visual weight balance** — Dark and light areas are distributed intentionally across the viewport
- [ ] **Responsive elegance** — The design adapts beautifully, not just functionally, at 375px / 768px / 1280px

### Uniqueness Verification

Ask these questions about the final output:

1. Could someone identify this as coming from a specific aesthetic direction? → If no, the design lacks commitment
2. Would this look identical to other AI-generated pages? → If yes, revisit typography and composition
3. Is there at least one visual element that surprises? → If no, add a signature detail
4. Does the motion feel orchestrated or random? → If random, simplify and focus on 2-3 key moments
