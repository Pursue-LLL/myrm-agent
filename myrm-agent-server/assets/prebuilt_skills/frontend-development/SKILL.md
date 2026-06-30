---
name: frontend-development
description: >-
  Production-grade frontend development workflow for React, Vue, and vanilla projects.
  Covers component architecture, responsive design, accessibility (WCAG 2.1 AA),
  performance optimization, and modern CSS (Tailwind / CSS Modules).
version: 1.0.0
category: development
tags:
  - frontend
  - react
  - vue
  - tailwind
  - accessibility
  - responsive
  - performance
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool grep_tool
contract:
  steps:
    - "Phase 1: Requirements — clarify framework, styling approach, target browsers, and scope"
    - "Phase 2: Architecture — plan component tree, state management, and file structure"
    - "Phase 3: Implement — build components following quality standards"
    - "Phase 4: Polish — accessibility audit, responsive check, performance review"
  potential_traps:
    - description: "Building a single monolithic component instead of composable pieces"
      mitigation: "Each component must have a single responsibility; extract when > 150 lines"
      severity: high
    - description: "Ignoring accessibility — no semantic HTML, missing ARIA labels, poor keyboard nav"
      mitigation: "Run the accessibility checklist in Phase 4 for every interactive element"
      severity: high
    - description: "Over-engineering state management for simple UIs"
      mitigation: "Use local state by default; lift state only when 2+ siblings need it; global store only for truly app-wide state"
      severity: medium
  verification_steps:
    - step_id: responsive_verified
      description: "Layout works at mobile (375px), tablet (768px), and desktop (1280px)"
      validation_method: "Visual check or media query breakpoints present in styles"
      is_required: true
    - step_id: accessibility_checked
      description: "All interactive elements are keyboard accessible with proper ARIA attributes"
      validation_method: "Phase 4 accessibility checklist completed"
      is_required: true
  success_criteria: "Production-ready components that are responsive, accessible, performant, and maintainable"
  estimated_duration_seconds: 1800
---

# Frontend Development

## Overview

Good frontend code is invisible to users — it just works: fast loads, smooth interactions, readable on any device, usable with keyboard or screen reader. This workflow ensures every piece of frontend code meets production standards, not just "it renders."

## Phase 1: Requirements

Before writing any component:

1. **Framework** — React? Vue? Vanilla? Next.js / Nuxt?
2. **Styling** — Tailwind CSS? CSS Modules? Styled-components? Plain CSS?
3. **Target** — Desktop only? Mobile-first? Which browsers?
4. **Scope** — Single component? Full page? Multi-page feature?
5. **Data** — Where does data come from? API? Props? Local state?

If not specified, default to: React + Tailwind CSS, mobile-first, modern browsers.

## Phase 2: Architecture

### Component Tree Design

Before coding, sketch the component hierarchy:

```
PageLayout
├── Header (nav, user menu)
├── MainContent
│   ├── FilterBar (search, filters)
│   ├── DataTable / CardGrid
│   │   └── TableRow / Card (repeating unit)
│   └── Pagination
└── Footer
```

### Design Principles

1. **Single Responsibility** — One component, one job. Extract when > 150 lines.
2. **Props Down, Events Up** — Parent passes data; child emits events.
3. **Colocation** — Keep styles, types, and tests next to the component.
4. **Composition Over Configuration** — Prefer `children` / slots over boolean prop explosions.

### State Management Decision Tree

```
Does only this component need the state?
├── Yes → useState / ref (local state)
└── No → Do 2+ sibling components need it?
    ├── Yes → Lift to nearest shared parent
    └── No → Is it truly app-wide (auth, theme, notifications)?
        ├── Yes → Context / Pinia / Zustand
        └── No → Lift to parent (you're probably overthinking it)
```

### File Structure

```
components/
├── UserTable/
│   ├── UserTable.tsx        # Component
│   ├── UserTable.test.tsx   # Tests
│   ├── UserTableRow.tsx     # Sub-component
│   └── index.ts             # Public export
```

## Phase 3: Implement

### React Component Template

```tsx
interface UserCardProps {
  user: User;
  onEdit: (id: string) => void;
}

export function UserCard({ user, onEdit }: UserCardProps) {
  return (
    <article
      className="rounded-lg border border-gray-200 p-4 transition-shadow hover:shadow-md"
      aria-label={`User card for ${user.name}`}
    >
      <div className="flex items-center gap-3">
        <img
          src={user.avatar}
          alt=""
          className="h-10 w-10 rounded-full object-cover"
          loading="lazy"
        />
        <div className="min-w-0 flex-1">
          <h3 className="truncate text-sm font-medium text-gray-900">
            {user.name}
          </h3>
          <p className="truncate text-sm text-gray-500">{user.email}</p>
        </div>
        <button
          onClick={() => onEdit(user.id)}
          className="rounded-md px-3 py-1.5 text-sm font-medium text-blue-600 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          aria-label={`Edit ${user.name}`}
        >
          Edit
        </button>
      </div>
    </article>
  );
}
```

### Coding Standards

| Rule | Rationale |
|------|-----------|
| Explicit TypeScript interfaces for all props | Catch misuse at compile time |
| Semantic HTML elements (`article`, `nav`, `main`, `section`) | Screen readers and SEO |
| `loading="lazy"` on images below the fold | Reduce initial page weight |
| `min-w-0` on flex children with text | Prevent flex item overflow |
| `truncate` for user-generated text | Prevent layout breaks |
| Focus-visible styles on all interactive elements | Keyboard accessibility |
| Event handlers as props, not inline logic | Testability and reuse |

### Responsive Design

Mobile-first approach — write base styles for mobile, add breakpoints for larger screens:

```tsx
<div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
  {users.map(user => <UserCard key={user.id} user={user} />)}
</div>
```

### Breakpoints Reference

| Breakpoint | Width | Target |
|------------|-------|--------|
| Default | 0-639px | Mobile |
| `sm` | 640px+ | Large phone / small tablet |
| `md` | 768px+ | Tablet |
| `lg` | 1024px+ | Laptop |
| `xl` | 1280px+ | Desktop |
| `2xl` | 1536px+ | Large desktop |

### Common Layout Patterns

```tsx
/* Centered max-width container */
<div className="mx-auto max-w-7xl px-4 sm:px-6 lg:px-8">

/* Sticky header */
<header className="sticky top-0 z-10 border-b bg-white/80 backdrop-blur">

/* Sidebar + main layout */
<div className="flex">
  <aside className="hidden w-64 shrink-0 lg:block">
  <main className="min-w-0 flex-1">
</div>
```

## Phase 4: Polish

### Accessibility Checklist

Run through for every interactive element:

- [ ] **Semantic HTML** — Using `button` not `div` for clickable elements
- [ ] **Alt text** — All `img` tags have descriptive `alt` (or `alt=""` for decorative)
- [ ] **Keyboard navigation** — All interactive elements reachable via Tab; Enter/Space activates
- [ ] **Focus indicators** — Visible `focus:ring` or `focus-visible:outline` on all focusable elements
- [ ] **ARIA labels** — Non-text interactive elements have `aria-label` or `aria-labelledby`
- [ ] **Color contrast** — Text meets WCAG AA (4.5:1 for normal text, 3:1 for large)
- [ ] **Form labels** — Every `input` has an associated `label` (or `aria-label`)
- [ ] **Error states** — Form errors announced to screen readers (`aria-invalid`, `aria-describedby`)
- [ ] **Skip link** — "Skip to main content" link for keyboard users (on full pages)

### Performance Checklist

- [ ] **Images** — Use `loading="lazy"`, appropriate sizes, WebP/AVIF format
- [ ] **Bundle** — No unnecessary dependencies; tree-shakeable imports
- [ ] **Renders** — No unnecessary re-renders; memoize expensive computations
- [ ] **Lists** — Virtualize lists > 100 items (react-window / @tanstack/virtual)
- [ ] **Fonts** — `font-display: swap`; subset to used characters if custom font
- [ ] **CSS** — Purge unused styles; avoid runtime CSS-in-JS for static styles

### Responsive Verification

Test at these widths (or use Tailwind responsive variants):

| Width | Device | What to Check |
|-------|--------|---------------|
| 375px | iPhone SE | Nothing overflows; text readable |
| 768px | iPad | Grid switches to 2-column |
| 1280px | Desktop | Full layout; sidebar visible |
| 1920px | Full HD | Content doesn't stretch too wide |

## Prebuilt Preview Environment

When generating React code for the preview sandbox, these tools are available at runtime:

**Preloaded:** `clsx`, `class-variance-authority`, `tailwind-merge`, `framer-motion`, `lucide-react`, `recharts`, `date-fns`, `zustand`, `react-hook-form`

**Auto-detected on import:** All `@radix-ui/react-*` primitives (dialog, select, tabs, switch, checkbox, accordion, avatar, progress, slider, toast, and more)

**Prebuilt utility:** `cn()` function at `./lib/utils` — combines `clsx` + `tailwind-merge` for intelligent className merging (Shadcn UI pattern)

```tsx
import { cn } from './lib/utils';
import * as Dialog from '@radix-ui/react-dialog';

<Dialog.Root>
  <Dialog.Trigger className={cn("px-4 py-2 rounded-md", isPrimary && "bg-primary text-white")}>
    Open
  </Dialog.Trigger>
</Dialog.Root>
```
