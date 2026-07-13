---
name: obsidian-bases
description: >-
  Create and edit Obsidian Bases (.base files) — database-like views of vault
  notes with filters, formulas, summaries, and multiple view types
  (table, cards, list, map).
version: 1.0.0
category: productivity
tags:
  - obsidian
  - bases
  - database
  - filters
  - formulas
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Locate — find the Obsidian vault and decide where to place the .base file"
    - "Phase 2: Design — plan filters, formulas, and view layout based on user requirements"
    - "Phase 3: Build — write valid YAML with correct quoting and formula syntax"
    - "Phase 4: Validate — verify YAML parses cleanly and all formula/property references exist"
  potential_traps:
    - description: "YAML quoting errors — unquoted special characters cause parse failures"
      mitigation: "Wrap formulas containing double quotes in single quotes; quote strings with colons"
      severity: high
    - description: "Calling .round() on Duration instead of accessing .days first"
      mitigation: "Date subtraction returns Duration; always access .days/.hours first, then .round()"
      severity: high
    - description: "Referencing formula.X in order/properties without defining X in formulas section"
      mitigation: "Verify every formula.X reference has a matching entry in the formulas section"
      severity: high
    - description: "Missing null checks in formulas — crashes when properties are empty"
      mitigation: "Guard property access with if(): if(due_date, expr, fallback)"
      severity: medium
    - description: "Using Dataview syntax instead of Bases syntax"
      mitigation: "Bases uses its own filter/formula language, not Dataview; check syntax carefully"
      severity: medium
  verification_steps:
    - step_id: vault_found
      description: "Obsidian vault directory located and accessible"
      validation_method: "Directory contains .obsidian/ subfolder"
      is_required: true
    - step_id: yaml_valid
      description: "Generated .base file is valid YAML"
      validation_method: "Parse the YAML without errors"
      is_required: true
    - step_id: refs_resolve
      description: "All formula.X references in order/properties have matching formula definitions"
      validation_method: "Cross-check order and properties entries against formulas keys"
      is_required: true
  success_criteria: "A .base file that opens in Obsidian showing the expected filtered and formatted view"
  estimated_duration_seconds: 300
---

# Obsidian Bases

Create and edit `.base` files — YAML-based database views of vault notes.

## File Format

Base files use the `.base` extension and contain valid YAML.

```yaml
filters:
  and:
    - 'status == "active"'

formulas:
  days_old: '(now() - file.ctime).days'

properties:
  formula.days_old:
    displayName: "Age (days)"

views:
  - type: table
    name: "Active Items"
    order:
      - file.name
      - status
      - formula.days_old
```

## Filters

Narrow which notes appear. Applied globally or per-view.

### Operators

| Operator | Description |
|----------|-------------|
| `==` | equals |
| `!=` | not equal |
| `>`, `<`, `>=`, `<=` | comparison |
| `&&` | logical and |
| `\|\|` | logical or |
| `!` | logical not |

### Structure

```yaml
# Single filter
filters: 'status == "done"'

# AND — all must be true
filters:
  and:
    - 'status == "done"'
    - 'priority > 3'

# OR — any can be true
filters:
  or:
    - file.hasTag("book")
    - file.hasTag("article")

# NOT — exclude matches
filters:
  not:
    - file.hasTag("archived")

# Nested
filters:
  or:
    - file.hasTag("tag")
    - and:
        - file.hasTag("book")
        - file.hasLink("Textbook")
```

### File Functions in Filters

- `file.hasTag("tagname")` — note has this tag
- `file.hasLink("NoteName")` — note links to this file
- `file.inFolder("FolderName")` — note is in this folder

## Properties

Three types:

1. **Note properties** — from frontmatter: `author`, `status`, `due_date`
2. **File properties** — file metadata (see table below)
3. **Formula properties** — computed: `formula.my_formula`

### File Properties

| Property | Type | Description |
|----------|------|-------------|
| `file.name` | String | File name |
| `file.basename` | String | Name without extension |
| `file.path` | String | Full path |
| `file.folder` | String | Parent folder |
| `file.ext` | String | Extension |
| `file.size` | Number | Size in bytes |
| `file.ctime` | Date | Created time |
| `file.mtime` | Date | Modified time |
| `file.tags` | List | All tags |
| `file.links` | List | Internal links |
| `file.backlinks` | List | Files linking here |

### Display Names

```yaml
properties:
  status:
    displayName: "Status"
  formula.days_old:
    displayName: "Age"
```

## Formulas

Computed properties defined in the `formulas` section.

```yaml
formulas:
  total: "price * quantity"
  status_icon: 'if(done, "✅", "⏳")'
  created: 'file.ctime.format("YYYY-MM-DD")'
  days_old: '(now() - file.ctime).days'
  days_until: 'if(due_date, (date(due_date) - today()).days, "")'
```

### Key Functions

| Function | Description |
|----------|-------------|
| `date(string)` | Parse to date (`YYYY-MM-DD HH:mm:ss`) |
| `now()` | Current date and time |
| `today()` | Current date (time = 00:00:00) |
| `if(cond, true, false?)` | Conditional |
| `duration(string)` | Parse duration |
| `file(path)` | Get file object |
| `link(path, display?)` | Create a link |

### Duration Type

Date subtraction returns a **Duration**, not a number.

```yaml
# CORRECT — access .days first, then use number functions
"(now() - file.ctime).days"
"(date(due_date) - today()).days.round(0)"

# WRONG — Duration doesn't support .round() directly
# "(now() - file.ctime).round(0)"
```

**Duration fields:** `.days`, `.hours`, `.minutes`, `.seconds`, `.milliseconds`

### Date Arithmetic

```yaml
'now() + "1 day"'
'today() + "7d"'
'now() - file.ctime'         # Returns Duration
'(now() - file.ctime).days'  # Number
```

Duration units: `y/year/years`, `M/month/months`, `d/day/days`, `w/week/weeks`, `h/hour/hours`, `m/minute/minutes`, `s/second/seconds`

### Null Guards

Properties may not exist on all notes. Always guard with `if()`:

```yaml
# WRONG — crashes if due_date is empty
'(date(due_date) - today()).days'

# CORRECT
'if(due_date, (date(due_date) - today()).days, "")'
```

## Views

### Table

```yaml
views:
  - type: table
    name: "Tasks"
    order:
      - file.name
      - status
      - due_date
    summaries:
      price: Sum
      count: Average
```

### Cards

```yaml
views:
  - type: cards
    name: "Gallery"
    order:
      - cover_image
      - file.name
      - description
```

### List

```yaml
views:
  - type: list
    name: "Simple"
    order:
      - file.name
      - status
```

### Map

Requires latitude/longitude properties and the Maps community plugin.

### View Options

| Option | Description |
|--------|-------------|
| `limit` | Max results |
| `groupBy.property` | Group by this property |
| `groupBy.direction` | `ASC` or `DESC` |
| `filters` | View-specific filters (same syntax as global) |
| `summaries` | Map properties to summary formulas |

## Summary Formulas

| Name | Input | Description |
|------|-------|-------------|
| `Average` | Number | Mean |
| `Sum` | Number | Total |
| `Min` / `Max` | Number | Extremes |
| `Median` | Number | Median |
| `Range` | Number | Max − Min |
| `Stddev` | Number | Standard deviation |
| `Earliest` / `Latest` | Date | Date extremes |
| `Checked` / `Unchecked` | Boolean | Count true/false |
| `Empty` / `Filled` | Any | Count empty/non-empty |
| `Unique` | Any | Count distinct values |

Custom summaries:

```yaml
summaries:
  weighted_avg: 'values.mean().round(3)'
```

## Complete Example: Task Tracker

```yaml
filters:
  and:
    - file.hasTag("task")
    - 'file.ext == "md"'

formulas:
  days_until_due: 'if(due, (date(due) - today()).days, "")'
  is_overdue: 'if(due, date(due) < today() && status != "done", false)'
  priority_label: 'if(priority == 1, "🔴 High", if(priority == 2, "🟡 Medium", "🟢 Low"))'

properties:
  formula.days_until_due:
    displayName: "Days Until Due"
  formula.priority_label:
    displayName: "Priority"

views:
  - type: table
    name: "Active Tasks"
    filters:
      and:
        - 'status != "done"'
    order:
      - file.name
      - status
      - formula.priority_label
      - due
      - formula.days_until_due
    groupBy:
      property: status
      direction: ASC
    summaries:
      formula.days_until_due: Average

  - type: table
    name: "Completed"
    filters:
      and:
        - 'status == "done"'
    order:
      - file.name
      - completed_date
```

## Embedding

```markdown
![[MyBase.base]]
![[MyBase.base#View Name]]
```

## YAML Quoting Rules

- Wrap formulas containing double quotes in **single quotes**: `'if(done, "Yes", "No")'`
- Quote strings with special YAML characters (`: { } [ ] , & * # ? | - < > = ! % @`)
- Use double quotes for simple display names: `"My View"`

```yaml
# WRONG
displayName: Status: Active

# CORRECT
displayName: "Status: Active"

# WRONG — double quotes inside double quotes
label: "if(done, "Yes", "No")"

# CORRECT — single quotes wrapping double quotes
label: 'if(done, "Yes", "No")'
```
