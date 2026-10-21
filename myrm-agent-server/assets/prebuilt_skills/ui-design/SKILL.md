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
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool grep_tool file_edit_tool browser_navigate_tool
contract:
  steps:
    - "Phase 1: Design Intent — understand purpose, audience, declare surface archetype, and commit to a bold aesthetic direction"
    - "Phase 2: Visual System — establish typography, color palette, spatial rhythm, and motion language"
    - "Phase 3: Implement — build production-grade code with meticulous aesthetic execution"
    - "Phase 4: Refine — audit visual cohesion, motion polish, responsive elegance, and 10-Tell Slop Diagnostic (≥8/10)"
  potential_traps:
    - description: "Destroying existing business logic via full file rewrite during redesign"
      mitigation: "When restyling existing components, MUST use file_edit_tool for incremental edits; preserve all existing TypeScript props, state, hooks, and event callbacks"
      severity: critical
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
    - step_id: existing_logic_preserved
      description: "Existing business logic, TypeScript interfaces, and React state/hooks remain completely intact during restyling"
      validation_method: "Ensure no props, state hooks, internationalization (useTranslations), or event handlers were removed or broken"
      is_required: true
    - step_id: aesthetic_direction_set
      description: "A clear surface archetype and intentional aesthetic direction are chosen before coding"
      validation_method: "Design intent statement exists with surface archetype, tone, differentiation, and font/color choices"
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
    - step_id: visual_verified
      description: "HTML artifact rendered correctly in browser — layout, colors, and interactions match intent"
      validation_method: "browser_navigate_tool with verify_goal scores ≥4/5"
      is_required: false
  success_criteria: "A visually striking, production-ready interface with a clear aesthetic identity that feels genuinely designed, not AI-generated"
  estimated_duration_seconds: 2400
---

# UI Design

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.

## Related Skills

- **`popular-web-designs`** — 54 real-world brand design systems (Stripe, Linear, Vercel, etc.) with exact CSS tokens. Pair with this skill: use `ui-design` for the design *process and taste*, then pull specific color palettes, font stacks, and component specs from `popular-web-designs` when styling after a known brand.
- **`infographic`** — 21 layouts × 21 styles for generating infographics and visual summaries. Use when the deliverable is a data-driven visual rather than a full UI page.

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
Surface archetype: [Editorial / Dashboard / Catalog / Canvas / Wizard / Conversational / Landing / Custom: ...]
Aesthetic: [chosen direction]
Signature element: [the unforgettable detail]
Font pairing: [display font] + [body font]
Color strategy: [dominant/accent approach]
Motion philosophy: [restrained elegance / orchestrated drama / etc.]
```

### Surface-First: Composition Archetype

Before designing any element, **declare** the composition archetype. This is the single highest-leverage decision — it prevents the LLM default of "hero + 3 cards + CTA footer" regardless of content.

| Archetype | When to Use | Key Constraint |
|-----------|-------------|----------------|
| **Editorial** | Long-form content, storytelling, blogs | Generous whitespace, drop caps, pull quotes; **no card grids** |
| **Dashboard** | Monitoring, analytics, data-dense views | Density-first; **no hero sections**, minimal decorative space |
| **Catalog** | Products, portfolios, collections | Grid/masonry dominates; **filtering is the UX**, not marketing copy |
| **Canvas** | Tools, editors, creative apps | Toolbars at edges, content fills center; **no page chrome** |
| **Wizard** | Onboarding, multi-step forms, setup flows | Single focus per step; progress indicator; **no distractions** |
| **Conversational** | Chat, messaging, support interfaces | Message-bubble rhythm; input at bottom; **no sidebars** |
| **Landing** | Marketing, product launches, announcements | Hero is acceptable here (and only here); scroll-driven narrative |

**Rules:**
1. State the archetype at the top of the Design Intent Statement before any visual choices
2. The archetype dictates layout structure — visual techniques (Phase 3) work *within* this frame
3. If the content matches no archetype, declare "Custom" and describe the structural constraint

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

### 10-Tell Slop Diagnostic

Score the output against these 10 common AI-design flaws. Each item scores 0 (present) or 1 (absent). **Minimum passing score: 8/10.** Any score below → fix before delivery.

| # | Tell | What to Look For |
|---|------|-----------------|
| 1 | **Generic hero** | Full-width hero with centered H1 + subtitle + CTA button when the archetype doesn't call for it |
| 2 | **Card trinity** | Exactly 3 feature cards in a row with icon + title + paragraph |
| 3 | **Purple/blue gradient** | Default AI color palette — purple-to-blue gradients without conceptual justification |
| 4 | **Inter/system font** | Using Inter, Roboto, Arial, or system-ui as the primary display font |
| 5 | **Symmetry everywhere** | Every section perfectly centered; no asymmetry, overlap, or tension |
| 6 | **Decoration without meaning** | Floating blobs, random dots, gradient orbs that serve no informational purpose |
| 7 | **Uniform spacing** | Every section has identical padding; no rhythm variation or density contrast |
| 8 | **Stock motion** | `transition-all duration-300` on everything; no orchestrated timing or meaningful easing |
| 9 | **No signature element** | Nothing memorable; remove the logo and it could be any product |
| 10 | **Responsive afterthought** | Mobile is just "stack everything vertically" with no design adaptation |

**Scoring & repair:**
- **8-10**: Ship it
- **5-7**: Fix the failing tells — each has a direct remedy in Phase 2/3
- **Below 5**: Restart from Phase 1 — the design intent was too weak

### Visual Verification (when browser available)

After writing the HTML artifact, verify rendering accuracy before delivery:

1. Serve the file locally in background: `bash_code_execute_tool(command="python -m http.server 8765", run_in_background=true)`
2. Navigate with verification goal:
   ```
   browser_navigate_tool(url="http://localhost:8765/artifact.html", verify_goal="<describe expected layout, colors, and key elements>")
   ```
3. The tool automatically runs a 3-layer visual check (DOM presence → screenshot comparison → Vision LLM scoring 1-5)
4. If score < 3: read the feedback, fix the issues, re-verify
5. If score ≥ 4: kill the background server and proceed to delivery

This step is optional — skip if browser tools are unavailable or the deliverable is a code component (not standalone HTML).

## Sandpack Runtime Environment

When generating React code for preview, the following packages are pre-installed in the runtime:

### Always Available (Preloaded)

- `clsx` — conditional className composition
- `class-variance-authority` — component variant definitions (cva)
- `tailwind-merge` — intelligent Tailwind class merging
- `framer-motion` — animation and motion library
- `lucide-react` — icon library
- `recharts` — charting library
- `date-fns` — date utilities
- `zustand` — lightweight state management
- `react-hook-form` — form handling

### Available on Import (Auto-Detected)

All Radix UI primitives are available — just `import` them and the runtime will install automatically:

`@radix-ui/react-accordion`, `alert-dialog`, `avatar`, `checkbox`, `collapsible`, `context-menu`, `dialog`, `dropdown-menu`, `hover-card`, `label`, `menubar`, `navigation-menu`, `popover`, `progress`, `radio-group`, `scroll-area`, `select`, `separator`, `slider`, `slot`, `switch`, `tabs`, `toast`, `toggle`, `toggle-group`, `tooltip`

### Prebuilt Utility: `cn()`

A `cn()` utility function is pre-installed at `/lib/utils.js` — the Shadcn UI standard pattern:

```tsx
import { cn } from './lib/utils';

<button className={cn(
  "px-4 py-2 rounded-md font-medium transition-colors",
  variant === "destructive" && "bg-destructive text-destructive-foreground",
  disabled && "opacity-50 cursor-not-allowed"
)}>
```

### Recommended Pattern: Radix + cn() + Tailwind

Build Shadcn-quality components by combining Radix primitives with `cn()` and Tailwind:

```tsx
import * as SwitchPrimitive from '@radix-ui/react-switch';
import { cn } from './lib/utils';

function Switch({ className, ...props }) {
  return (
    <SwitchPrimitive.Root
      className={cn(
        "peer inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full",
        "border-2 border-transparent shadow-sm transition-colors",
        "data-[state=checked]:bg-primary data-[state=unchecked]:bg-input",
        className
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        className={cn(
          "pointer-events-none block h-4 w-4 rounded-full bg-background shadow-lg",
          "transition-transform data-[state=checked]:translate-x-4 data-[state=unchecked]:translate-x-0"
        )}
      />
    </SwitchPrimitive.Root>
  );
}
