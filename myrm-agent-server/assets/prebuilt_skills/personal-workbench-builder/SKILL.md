---
name: personal-workbench-builder
description: >-
  Build single-file, responsive, zero-CDN, theme-aware personal life and productivity workbench widgets in HTML. Integrates 8 core modules (habits, pomodoro, tasks, launcher, expenses, countdowns, health, scratchpad) with local storage persistence via Myrm Widget Theme Bridge.
version: 1.0.0
category: productivity
tags:
  - workbench
  - productivity
  - dashboard
  - widget
  - html-artifact
allowed-tools: file_write_tool file_read_tool
contract:
  steps:
    - "Analyze user requirements and select relevant modules from the 8-module suite"
    - "Design a cohesive responsive CSS Grid / Flexbox layout using Myrm CSS custom properties (--background, --foreground, --card, --primary, etc.)"
    - "Implement interactive JavaScript with zero external CDN dependencies and automatic localStorage persistence"
    - "Output the self-contained HTML artifact for sandboxed execution in Myrm MediaPreview"
  verification_steps:
    - step_id: zero_cdn_check
      description: "Verify that no external CDN scripts or stylesheet tags are used (no cdn.tailwindcss.com, no external fonts)"
      validation_method: output_contains_no_external_scripts
    - step_id: theme_bridge_compliance
      description: "Verify that CSS styles consume standard host CSS variables"
      validation_method: output_contains_css_variables
    - step_id: localstorage_persistence
      description: "Verify that user state changes are saved to and restored from localStorage"
      validation_method: output_contains_localstorage_calls
---

# personal-workbench-builder

You specialize in constructing **single-file, interactive personal workbenches and micro-applications** rendered within the Myrm sandboxed HTML artifact preview (`MediaPreview.tsx`).

Users need lightweight, persistent dashboards that combine daily productivity, habit tracking, and personal organization without heavyweight external installations.

---

## Hard Rules

1. **Zero External CDN Dependencies**:
   - **NEVER** include `<script src="https://cdn.tailwindcss.com">` or external CSS/JS libraries.
   - All styles must be self-contained within `<style>` tags using standard modern CSS (Flexbox, CSS Grid, CSS transitions).
   - All icons should use clean inline SVG or Unicode glyphs.

2. **Full Theme Bridge Compatibility**:
   - The host application automatically injects CSS variables via `Widget Theme Bridge`.
   - Your styles **MUST** bind directly to these host variables:
     - `background-color: var(--background, #ffffff);`
     - `color: var(--foreground, #09090b);`
     - Cards/panels: `background-color: var(--card, #ffffff); border: 1px solid var(--border, #e4e4e7); border-radius: var(--radius, 12px);`
     - Accents & buttons: `background-color: var(--primary, #18181b); color: var(--primary-foreground, #fafafa);`
     - Secondary surfaces: `var(--muted, #f4f4f5); var(--muted-foreground, #71717a);`
     - Dynamic dark mode styling can leverage `[data-theme="dark"]` or checking `var(--is-dark) === '1'`.

3. **Persistent Local State**:
   - The Myrm sandbox bridges `localStorage` into persistent workspace KV storage.
   - Every interactive element (checkmarks, inputs, sliders, counters, timers) **MUST** immediately synchronize with `localStorage` upon state changes.
   - Key names should be namespaced (e.g., `myrm_workbench_habits_v1`, `myrm_workbench_tasks_v1`).

4. **Single-File Self-Contained Deliverable**:
   - Output must be a complete HTML document starting with `<!DOCTYPE html>` containing `<head>`, `<style>`, `<body>`, and `<script>`.
   - Output directly as an HTML code block or write to a target `.html` file.

---

## The 8-Module Suite Architecture

When building a personal workbench, select and combine from the following standard 8 modules according to user goals:

### 1. Habit Tracker (习惯打卡)
- **Features**: Visual weekday check grid (Mon-Sun), consecutive streak counter, completion percentage.
- **State Schema**: `Record<string, boolean[]>` mapping habit names to 7-day or 30-day boolean arrays.
- **Micro-interaction**: Satisfying click toggle with subtle scale transition and streak calculation.

### 2. Pomodoro Focus Timer (番茄专注钟)
- **Features**: 25m work / 5m short break / 15m long break toggle, circular or linear progress bar, start/pause/reset controls, session counter.
- **State Schema**: `{ mode: 'work'|'break', timeLeft: number, isRunning: boolean, completedRounds: number }`.

### 3. Daily Priority Matrix & Tasks (待办看板与四象限)
- **Features**: Quick input for new tasks, filter by priority (Urgent/Important Eisenhower quadrants or Today/Upcoming), checkbox completion, trash removal.
- **State Schema**: `Array<{ id: string, title: string, priority: 'urgent'|'normal'|'low', done: boolean, createdAt: number }>`.

### 4. Quick Launcher & Bookmarks (效率启动盘)
- **Features**: Organized link grid by category (Work, Docs, Tools, Social), custom link modal/input, target="_blank" safe anchors.
- **State Schema**: `Array<{ id: string, title: string, url: string, category: string, icon: string }>`.

### 5. Micro Expense Ledger (日常轻记账)
- **Features**: Fast record of amount, category (Meals, Transport, Shopping, Bills), date, monthly total sum, and recent transaction list.
- **State Schema**: `Array<{ id: string, amount: number, category: string, note: string, timestamp: number }>`.

### 6. Goal & Event Countdown (目标倒数日)
- **Features**: Days remaining calculator, percentage elapsed bar, target date badge.
- **State Schema**: `Array<{ id: string, title: string, targetDate: string, category: string }>`.

### 7. Health & Hydration Tracker (健康饮水与体态)
- **Features**: 8-cup water progress meter (e.g., 2000ml goal), one-tap cup logging, sedentary stretch reminder timer.
- **State Schema**: `{ currentMl: number, targetMl: number, lastResetDate: string }`.

### 8. Inspiration Scratchpad (灵感便签墙)
- **Features**: Auto-saving rich text area or sticky card deck, tag filters, quick copy button.
- **State Schema**: `Array<{ id: string, content: string, color: string, updatedAt: number }>`.

---

## Standard Responsive Grid Layout

Organize modules into a responsive layout that flows seamlessly on both mobile (single column) and desktop (multi-column dashboard):

```css
.workbench-container {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  gap: 16px;
  padding: 20px;
  max-width: 1400px;
  margin: 0 auto;
}

.module-card {
  background: var(--card, #ffffff);
  border: 1px solid var(--border, #e4e4e7);
  border-radius: var(--radius, 12px);
  padding: 18px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  display: flex;
  flex-direction: column;
}
```

---

## LocalStorage Polyfill Pattern

Always wrap `localStorage` access in safe helper functions to prevent exceptions in restrictive sandbox environments:

```javascript
const StorageHelper = {
  get(key, defaultValue) {
    try {
      const item = localStorage.getItem(key);
      return item ? JSON.parse(item) : defaultValue;
    } catch (e) {
      console.warn('Storage read failed:', e);
      return defaultValue;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch (e) {
      console.warn('Storage write failed:', e);
    }
  }
};
```

---

## Workflow

1. **Requirement Clarification**: Ask the user what focus areas they want (e.g., "Full 8-Module Life Suite" vs "Work Productivity Focus: Tasks + Pomodoro + Scratchpad").
2. **HTML & CSS Generation**: Produce the self-contained HTML document binding host CSS custom properties and responsive grid styling.
3. **Interactive JavaScript Execution**: Ensure all stateful modules restore saved data on `DOMContentLoaded` and save updates on every user interaction.
4. **Validation**: Check that the generated artifact contains NO external CDN URLs and validates gracefully.
