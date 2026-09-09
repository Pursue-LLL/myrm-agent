---
name: personal-life-workbench
description: >-
  Generate production-grade, self-contained interactive personal life workbenches and productivity dashboards.
  Integrates 8 core modular widgets (Eisenhower Todos, Habit Streaks, Pomodoro Timer, Quick Notes, Daily Reflection,
  Wellness Tracker, Quick Links, Countdown Milestones) with zero external CDN dependencies, native widget-theme-bridge
  dark/light synchronization, and local storage state persistence.
version: 1.0.0
category: productivity
tags:
  - workbench
  - productivity
  - life-dashboard
  - interactive-widget
  - local-storage
allowed-tools: file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Scope & Layout — Select 3 to 8 workbench modules and arrange in a responsive card grid"
    - "Phase 2: Theme Integration — Bind CSS custom properties (--background, --foreground, --card, --primary, --border, --radius) conforming to widget-theme-bridge"
    - "Phase 3: State Persistence — Wire up localStorage keys with namespacing and debounced autosave"
    - "Phase 4: Deliver & Validate — Output a self-contained, clean single-file HTML artifact with zero external script/style dependencies"
  potential_traps:
    - description: "Loading unpkg or external CDNs that fail in sandboxed or offline iframes"
      mitigation: "Use 100% vanilla ES6+ and pure CSS; zero external script or link tags"
      severity: high
    - description: "Hardcoding colors (e.g. #fff, #000) leading to unreadable text when host switches theme"
      mitigation: "Strictly use theme bridge CSS variables (var(--card), var(--foreground), etc.) with sensible fallbacks"
      severity: high
    - description: "Timer memory leaks or non-cleared intervals crashing iframe"
      mitigation: "Clean up previous setInterval before starting new ones; handle page visibility"
      severity: medium
  verification_steps:
    - step_id: self_contained_verified
      description: "HTML artifact contains zero external network dependencies (no cdnjs, unpkg, google fonts)"
      validation_method: "Verify no external http/https src or href links exist in the output"
      is_required: true
    - step_id: theme_bridge_bound
      description: "All cards, text, and inputs reference theme CSS custom properties"
      validation_method: "Inspect CSS declarations for var(--foreground) and var(--card)"
      is_required: true
    - step_id: local_persistence_wired
      description: "All state mutations (todos, notes, habits) invoke localStorage with defensive JSON parsing"
      validation_method: "Verify try/catch wrapped localStorage.getItem and setItem usage"
      is_required: true
  success_criteria: "A beautiful, interactive, theme-adaptive, offline-persistent personal workbench artifact ready for instant user interaction."
  estimated_duration_seconds: 300
---

# Personal Life Workbench Builder

You are an expert Frontend Architect specializing in building self-contained, responsive, and persistent **Personal Life Workbenches & Productivity Dashboards**.

When the user asks for a daily dashboard, personal workbench, habit tracker, or life management widget, you construct an interactive, single-file HTML/CSS/JS artifact that seamlessly runs inside Myrm's sandboxed `HtmlPreview` environment.

---

## 1. Golden Rules & Architectural Constraints

1. **Zero External CDN Dependencies**:
   - 🚫 NEVER link to `https://cdnjs.cloudflare.com`, `unpkg.com`, `cdn.jsdelivr.net`, Google Fonts, or external scripts.
   - ✅ Use 100% pure vanilla JavaScript (ES6+) and embedded CSS. Use inline SVG icons instead of icon font libraries.
2. **Native Host Theme Synchronization (`widget-theme-bridge`)**:
   - The host application dynamically pushes CSS variables into the iframe. Your styles **must** rely on:
     - Backgrounds: `var(--background, #ffffff)`, `var(--card, #f8fafc)`, `var(--muted, #f1f5f9)`
     - Text colors: `var(--foreground, #0f172a)`, `var(--muted-foreground, #64748b)`
     - Accents: `var(--primary, #3b82f6)`, `var(--primary-foreground, #ffffff)`
     - Borders & Radii: `var(--border, #e2e8f0)`, `var(--radius, 0.75rem)`
3. **Robust State Persistence (`localStorage`)**:
   - The iframe environment provides a scoped `localStorage` polyfill bridged to the host.
   - Namespace all keys under `myrm_workbench_` (e.g. `myrm_workbench_todos`, `myrm_workbench_notes`).
   - Always wrap `localStorage.getItem()` and `localStorage.setItem()` in `try...catch` blocks to protect against parsing errors or quota limits.
   - Use debouncing (300-500ms) for high-frequency input (such as textareas / notes).
4. **Responsive Layout**:
   - Mobile-first responsive CSS grid (`grid-template-columns: repeat(auto-fit, minmax(280px, 1fr))`).
   - Touch-friendly tap targets (minimum 40px height for buttons and inputs).

---

## 2. The 8 Core Modular Widgets

A standard workbench selects 3 to 8 of the following modules based on user needs:

| Module | Core Features | State Schema |
|---|---|---|
| **1. Focus Todos** | Priority tagging, checkboxes, inline add/delete, progress bar | `[{ id, text, done, priority: 'high'\|'med'\|'low' }]` |
| **2. Habit Streaks** | Daily checkboxes, consecutive streak count, visual badges | `[{ id, name, lastCheckedDate, streakCount }]` |
| **3. Pomodoro Timer** | 25m focus / 5m break, play/pause/reset, SVG circular progress | `{ mode: 'focus'\|'break', timeLeft, isRunning }` |
| **4. Quick Notes** | Auto-saving scratchpad, character count, clear button | `string` (persisted on input debounced) |
| **5. Daily Reflection** | Mood selector (5 emoji/SVGs), gratitude prompt, daily log | `{ date, mood, gratitude, highlight }` |
| **6. Hydration Log** | 8-cup water intake tracker, quick tap to add, daily reset | `{ date, cups: number }` |
| **7. Launchpad** | Frequently visited tools/links, custom title, clean badges | `[{ title, url, icon }]` |
| **8. Countdown Tracker** | Target event date, remaining days/hours badge | `[{ event, targetDate }]` |

---

## 3. Standard Code Blueprint

Below is the verified, minimal structure for a production-grade workbench artifact:

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Personal Life Workbench</title>
  <style>
    :root {
      --bg: var(--background, #0f172a);
      --card-bg: var(--card, #1e293b);
      --text: var(--foreground, #f8fafc);
      --text-muted: var(--muted-foreground, #94a3b8);
      --border-color: var(--border, #334155);
      --accent: var(--primary, #3b82f6);
      --accent-fg: var(--primary-foreground, #ffffff);
      --radius-sm: var(--radius, 0.5rem);
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
    body { background-color: var(--bg); color: var(--text); padding: 1.25rem; transition: background-color 0.2s; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 1.25rem; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 1rem; }
    .card { background: var(--card-bg); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 1rem; }
    .card-title { font-size: 0.95rem; font-weight: 600; margin-bottom: 0.75rem; display: flex; align-items: center; justify-content: space-between; }
    button { background: var(--accent); color: var(--accent-fg); border: none; border-radius: 0.375rem; padding: 0.4rem 0.8rem; cursor: pointer; font-size: 0.85rem; }
    input, textarea { background: var(--bg); color: var(--text); border: 1px solid var(--border-color); border-radius: 0.375rem; padding: 0.4rem 0.6rem; width: 100%; }
  </style>
</head>
<body>
  <div class="header">
    <h2>个人效能与生活工作台</h2>
    <span id="date-display" style="font-size: 0.85rem; color: var(--text-muted);"></span>
  </div>

  <div class="grid">
    <!-- Card 1: 待办事项 -->
    <div class="card" id="todo-module">
      <div class="card-title"><span>今日重点待办</span><span id="todo-count" style="font-size:0.75rem; color:var(--text-muted);"></span></div>
      <div style="display:flex; gap:0.5rem; margin-bottom:0.75rem;">
        <input type="text" id="new-todo" placeholder="添加待办事项..." />
        <button id="add-todo-btn">添加</button>
      </div>
      <ul id="todo-list" style="list-style:none; max-height:200px; overflow-y:auto;"></ul>
    </div>

    <!-- Card 2: 习惯打卡 -->
    <div class="card" id="habit-module">
      <div class="card-title"><span>习惯追踪打卡</span></div>
      <div id="habit-list"></div>
    </div>

    <!-- Card 3: 灵感速记 -->
    <div class="card" id="note-module">
      <div class="card-title"><span>随手灵感便签</span><span style="font-size:0.75rem; color:var(--text-muted);">自动同步</span></div>
      <textarea id="quick-note" rows="5" placeholder="记录突发灵感或临时备忘..."></textarea>
    </div>
  </div>

  <script>
    const STORAGE_PREFIX = 'myrm_workbench_';
    function loadState(key, fallback) {
      try { const v = localStorage.getItem(STORAGE_PREFIX + key); return v ? JSON.parse(v) : fallback; }
      catch { return fallback; }
    }
    function saveState(key, data) {
      try { localStorage.setItem(STORAGE_PREFIX + key, JSON.stringify(data)); } catch(e) { console.warn('Storage save failed', e); }
    }

    // 日期渲染
    const now = new Date();
    document.getElementById('date-display').textContent = now.toLocaleDateString('zh-CN', { month: 'short', day: 'numeric', weekday: 'short' });

    // 待办逻辑
    let todos = loadState('todos', [
      { id: 1, text: '审阅周度工作产物与报告', done: false },
      { id: 2, text: '坚持 30 分钟有氧运动', done: true }
    ]);
    function renderTodos() {
      const list = document.getElementById('todo-list');
      list.innerHTML = '';
      todos.forEach(t => {
        const li = document.createElement('li');
        li.style.cssText = 'display:flex; align-items:center; justify-content:space-between; padding:0.35rem 0; font-size:0.875rem; border-bottom:1px solid var(--border-color);';
        li.innerHTML = `
          <label style="display:flex; align-items:center; gap:0.5rem; cursor:pointer;">
            <input type="checkbox" ${t.done ? 'checked' : ''} style="width:auto;" onchange="toggleTodo(${t.id})" />
            <span style="${t.done ? 'text-decoration:line-through; opacity:0.6;' : ''}">${t.text}</span>
          </label>
          <button onclick="removeTodo(${t.id})" style="background:transparent; color:var(--text-muted); padding:0 0.3rem;">×</button>
        `;
        list.appendChild(li);
      });
      document.getElementById('todo-count').textContent = `${todos.filter(t=>t.done).length}/${todos.length}`;
      saveState('todos', todos);
    }
    window.toggleTodo = (id) => { todos = todos.map(t => t.id === id ? { ...t, done: !t.done } : t); renderTodos(); };
    window.removeTodo = (id) => { todos = todos.filter(t => t.id !== id); renderTodos(); };
    document.getElementById('add-todo-btn').onclick = () => {
      const input = document.getElementById('new-todo');
      if (!input.value.trim()) return;
      todos.push({ id: Date.now(), text: input.value.trim(), done: false });
      input.value = '';
      renderTodos();
    };
    renderTodos();

    // 习惯打卡逻辑
    let habits = loadState('habits', [
      { id: 1, name: '晨间饮水 500ml', streak: 5, checkedDate: '' },
      { id: 2, name: '阅读深度文档 20min', streak: 12, checkedDate: '' }
    ]);
    const todayStr = now.toISOString().slice(0, 10);
    function renderHabits() {
      const el = document.getElementById('habit-list');
      el.innerHTML = '';
      habits.forEach(h => {
        const isCheckedToday = h.checkedDate === todayStr;
        const row = document.createElement('div');
        row.style.cssText = 'display:flex; justify-content:space-between; align-items:center; margin-bottom:0.5rem; font-size:0.875rem;';
        row.innerHTML = `
          <span>${h.name}</span>
          <div style="display:flex; align-items:center; gap:0.5rem;">
            <span style="font-size:0.75rem; color:var(--accent);">🔥 ${h.streak}天</span>
            <button onclick="toggleHabit(${h.id})" style="padding:0.25rem 0.6rem; background:${isCheckedToday ? 'var(--text-muted)' : 'var(--accent)'}">${isCheckedToday ? '已打卡' : '打卡'}</button>
          </div>
        `;
        el.appendChild(row);
      });
      saveState('habits', habits);
    }
    window.toggleHabit = (id) => {
      habits = habits.map(h => {
        if (h.id === id) {
          const wasChecked = h.checkedDate === todayStr;
          return {
            ...h,
            checkedDate: wasChecked ? '' : todayStr,
            streak: wasChecked ? Math.max(0, h.streak - 1) : h.streak + 1
          };
        }
        return h;
      });
      renderHabits();
    };
    renderHabits();

    // 便签自动保存逻辑（防抖）
    const noteArea = document.getElementById('quick-note');
    noteArea.value = loadState('note', '');
    let noteTimer;
    noteArea.addEventListener('input', (e) => {
      clearTimeout(noteTimer);
      noteTimer = setTimeout(() => saveState('note', e.target.value), 400);
    });
  </script>
</body>
</html>
```

---

## 4. Delivery Quality Gate

1. **Self-Contained Check**:
   - Must NOT contain `<script src="http...">` or `<link rel="stylesheet" href="http...">`.
2. **Persistence Check**:
   - Must use `localStorage` with namespace `myrm_workbench_*` and safe fallback defaults.
3. **Theme Bridge Check**:
   - Must use CSS variables (`var(--background)`, `var(--card)`, etc.) so it immediately adapts to Dark/Light mode in Myrm's preview window.
