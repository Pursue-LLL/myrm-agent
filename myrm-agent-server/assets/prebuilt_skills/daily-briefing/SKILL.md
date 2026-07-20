---
name: daily-briefing
description: >-
  Personalized daily briefing that aggregates pending tasks, memory-based context,
  weather, and news into a concise morning report. Designed for cron scheduling
  with multi-channel delivery.
version: 1.0.0
category: productivity
tags:
  - daily
  - briefing
  - morning
  - productivity
  - cron
  - digest
allowed-tools: memory_search_tool memory_save_tool kanban_list_tasks web_search_tool web_fetch_tool file_write_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Context Gathering — recall user preferences, habits, and timezone from memory"
    - "Phase 2: Schedule & Tasks — kanban tasks with due dates and time-bound items"
    - "Phase 3: External Intelligence — retrieve weather forecast and relevant news for user's interests"
    - "Phase 4: Memory-Augmented Enrichment — cross-reference schedule with past conversations for contextual reminders"
    - "Phase 5: Briefing Compilation — synthesize all data into a structured, scannable daily report"
  potential_traps:
    - description: "Too many data sources making the briefing overwhelming"
      mitigation: "Hard cap: max 5 schedule items, 5 tasks, 3 news items. Prioritize by urgency and relevance."
      severity: medium
    - description: "External API failures (weather/news) blocking the entire briefing"
      mitigation: "Treat external data as optional enrichment. Generate briefing even if external sources fail."
      severity: medium
    - description: "Stale or irrelevant memory recall polluting the briefing"
      mitigation: "Use time-scoped memory queries (last 7 days). Filter by relevance score > 0.7."
      severity: low
  verification_steps:
    - step_id: has_schedule_section
      description: "Briefing includes schedule (Google Calendar and/or kanban) or states none today"
      validation_method: "Output contains a Schedule section with events/tasks or empty-state message"
      is_required: true
    - step_id: has_tasks_section
      description: "Briefing includes pending tasks or explicitly states 'all tasks complete'"
      validation_method: "Output contains a Tasks section with items or completion message"
      is_required: true
    - step_id: scannable_format
      description: "Briefing is concise and scannable (not a wall of text)"
      validation_method: "Total output under 800 words; uses headers, bullets, and text urgency labels"
      is_required: true
    - step_id: actionable_items
      description: "At least one actionable insight or reminder is provided"
      validation_method: "Contains an 'Action Items' or 'Reminders' section with specific next steps"
      is_required: false
  success_criteria: "User receives a concise, personalized daily briefing covering schedule, tasks, and relevant context within 30 seconds"
  estimated_duration_seconds: 30
---

# Daily Briefing

## Overview

Start every day with clarity. This skill compiles pending tasks, contextual reminders from past conversations, and optional external intelligence (weather, news) into a single, scannable briefing.

Best used with **cron scheduling** for automatic daily delivery via your preferred channel (WeChat, Slack, email, etc.).

## Phase 1: Context Gathering

Before building the briefing, establish the user's context:

1. **Recall user preferences** via `memory_search_tool`:
   - Timezone and locale (for correct date/time formatting)
   - Preferred briefing style (concise vs. detailed)
   - Topics of interest (for news filtering)
   - Location (for weather)

2. **Determine today's date** in the user's timezone

If preferences aren't found in memory, use sensible defaults and note the gap in the briefing footer.

## Phase 2: Schedule & Tasks

### Google Calendar (Optional)

If `$GOOGLE_WORKSPACE_TOKEN` is available (user connected Google Workspace OAuth):

1. Use `bash_code_execute_tool` to run `python3 .claude/skills/google-workspace/scripts/google_api.py calendar-today` (token and timezone are injected automatically when OAuth is connected).
2. Merge calendar events with kanban time-bound items in the Schedule section.
3. Sort combined schedule by start time; deduplicate overlapping titles.
4. If OAuth is not connected or the API fails, skip silently — kanban-only schedule is acceptable.

### Today's Schedule (from Kanban + optional Calendar)

- List tasks with **due today** or explicit time windows in metadata
- Sort by urgency; flag items starting within 2 hours when time metadata exists
- If no time-bound items: state "No scheduled items today" in the Schedule section

### Pending Tasks

Use `kanban_list_tasks` with `include_stats=true` to get task overview:
- **Overdue tasks** — highlight with urgency marker
- **Due today** — list with deadlines
- **In progress** — show current work items
- Limit to top 5 most urgent tasks

## Phase 3: External Intelligence

### Weather (Optional)

Use `web_search_tool` to fetch today's weather for the user's location:
- Temperature range and conditions
- Rain/snow probability if > 30%
- Severe weather alerts

### News & Updates (Optional)

Use `web_search_tool` for the user's interest topics:
- Limit to 3 most relevant items
- One-line summary per item
- Only include genuinely significant developments (not noise)

If external sources fail, skip gracefully — these sections are enrichment, not core.

## Phase 4: Memory-Augmented Enrichment

This is what makes the briefing **personal** and distinguishes it from generic digest tools:

1. **Cross-reference today's kanban deadlines with memory**:
   - If a meeting participant was discussed recently, surface relevant context
   - If a project was mentioned in yesterday's conversation, add a reminder
   - Example: "10:00 Product Review — *you mentioned preparing a feedback report yesterday*"

2. **Surface recurring patterns**:
   - "You've had 3 meetings with Team A this week"
   - "This is the 3rd day the API refactor task is overdue"

3. **Recall yesterday's unfinished threads**:
   - Use `memory_search_tool` with time-scoped queries (last 24-48 hours)
   - Surface any "I'll do this tomorrow" or deferred items

## Phase 5: Briefing Compilation

### Output Format

```
Daily Briefing — {Date}, {Day of Week}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Today's Schedule
• 09:00 — Team standup
• 10:00 — Product review (context: you planned to share the feedback report)
• 14:00 — 1:1 with Alice
• No conflicts detected

Tasks Requiring Attention
• [URGENT] API refactor proposal — overdue by 2 days
• [TODAY] Review PR #142 — due today
• [IN PROGRESS] Update docs

Weather
Shanghai: 28°C, partly cloudy, 20% rain chance

News Highlights
• OpenAI releases GPT-5 with native tool use
• React 20 enters beta with server components v2

Reminders
• You mentioned wanting to follow up with Bob about the deployment timeline
• Weekly report is due Friday

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Have a productive day.
```

### Compilation Rules

1. **Be concise** — each item gets one line. No paragraphs.
2. **Prioritize by urgency** — overdue > today > upcoming
3. **Use text urgency labels** — `[URGENT]` overdue, `[TODAY]` due today, `[IN PROGRESS]` active work
4. **Include memory context inline** — parenthetical notes next to relevant items
5. **End with actionable reminders** — things the user explicitly or implicitly deferred
6. **Respect the cap** — max 5 events, 5 tasks, 3 news items, 3 reminders

### Adaptation

The briefing adapts based on available data:

| Available Data | Briefing Behavior |
|---------------|-------------------|
| Calendar + Tasks + Memory | Full briefing with calendar events and contextual enrichment |
| Tasks + Memory | Full briefing with contextual enrichment |
| Tasks only | Task-focused briefing |
| Calendar only | Schedule-focused briefing |
| No tasks | Memory-only briefing with news and weather |
| First-time user (no memory) | Minimal briefing with setup suggestions |

### Cron Scheduling

Recommended cron configuration for daily delivery:

```yaml
schedule: "0 8 * * *"          # Every day at 8:00 AM
job_type: agent
skill: daily-briefing
delivery:
  channel: wechat              # or slack, email, webhook
active_hours: "07:00-09:00"    # Only deliver during morning window
```

The briefing runs as an agent job, allowing it to use all available tools and memory for maximum personalization.
