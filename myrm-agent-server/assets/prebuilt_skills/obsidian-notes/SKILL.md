---
name: obsidian-notes
description: >-
  Manage Obsidian vaults: create notes, update daily journals, maintain MOCs
  (Maps of Content), manage tags, and build interconnected knowledge graphs
  via file operations on the vault directory.
version: 1.0.0
category: productivity
tags:
  - obsidian
  - notes
  - knowledge-management
  - zettelkasten
  - markdown
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Locate — find the Obsidian vault directory"
    - "Phase 2: Understand — scan vault structure and conventions"
    - "Phase 3: Execute — create or update notes following vault conventions"
    - "Phase 4: Link — ensure proper wiki-links and backlinks"
  potential_traps:
    - description: "Breaking existing wiki-links by renaming files"
      mitigation: "Search for [[filename]] references before renaming; update all occurrences"
      severity: high
    - description: "Not matching the user's existing note format"
      mitigation: "Read 2-3 existing notes to detect frontmatter schema and formatting conventions"
      severity: medium
  verification_steps:
    - step_id: vault_found
      description: "Obsidian vault directory located and accessible"
      validation_method: "Directory contains .obsidian/ subfolder"
      is_required: true
  success_criteria: "Notes created/updated following vault conventions with proper internal links"
  estimated_duration_seconds: 300
---

# Obsidian Notes

## Overview

Obsidian is a knowledge management tool built on local Markdown files. Since everything is plain text, this skill can directly read and write vault files to manage notes, journals, and knowledge graphs.

## Phase 1: Locate the Vault

An Obsidian vault is any directory containing a `.obsidian/` subfolder.

Common locations:
- `~/Documents/Obsidian/`
- `~/obsidian-vault/`
- `~/notes/`

Ask the user or search for `.obsidian/` directories in common locations.

## Phase 2: Understand Vault Conventions

Before creating anything, read 2-3 existing notes to detect:

### Frontmatter Schema

```yaml
---
title: Note Title
date: 2024-01-15
tags: [tag1, tag2]
aliases: [alternate name]
status: draft | published | archived
---
```

### Folder Structure

Common patterns:
- **Flat** — all notes in root, organized by links
- **PARA** — Projects / Areas / Resources / Archives
- **Zettelkasten** — Fleeting / Literature / Permanent notes
- **Date-based** — YYYY/MM/DD folders for daily notes
- **Topic-based** — Folders per topic or project

### Linking Conventions

- `[[Page Name]]` — wiki-link to another note
- `[[Page Name|Display Text]]` — aliased link
- `#tag` — inline tags
- `![[Image.png]]` — embedded media

## Phase 3: Execute Operations

### Create a New Note

1. Determine the correct folder based on vault conventions
2. Generate appropriate frontmatter (match existing schema)
3. Write content in Markdown
4. Add relevant `[[wiki-links]]` to connect with existing notes

### Daily Note

Standard daily note pattern:

```markdown
---
date: {{date}}
tags: [daily]
---

# {{date}}

## Tasks
- [ ] ...

## Notes
...

## Journal
...
```

### Meeting Note

```markdown
---
date: {{date}}
type: meeting
attendees: [Person A, Person B]
project: [[Project Name]]
---

# Meeting: {{title}}

## Agenda
1. ...

## Discussion
...

## Action Items
- [ ] @PersonA — task description — due: date
- [ ] @PersonB — task description — due: date
```

### Map of Content (MOC)

A MOC is an index note that organizes a topic:

```markdown
---
type: moc
tags: [moc, topic]
---

# Topic MOC

## Overview
Brief description of this knowledge area.

## Core Concepts
- [[Concept A]] — brief description
- [[Concept B]] — brief description

## Resources
- [[Resource 1]]
- [[Resource 2]]

## Open Questions
- Question to explore...
```

## Phase 4: Maintain Links

### Before Writing

1. Search existing notes for related content
2. Check if target `[[links]]` already exist as files
3. If creating a note that others should link to, search for mentions of the topic

### After Writing

1. Verify all `[[wiki-links]]` point to existing or intentionally new notes
2. If new note introduces a concept, consider updating the relevant MOC
3. Check that tags are consistent with vault conventions

### Batch Operations

For bulk note management:
- Use `bash_code_execute_tool` with `find` to locate files by pattern
- Use `file_read_tool` to scan content for broken links
- Use `file_write_tool` to update frontmatter across multiple notes

## Best Practices

- Match the user's existing style — don't impose your own formatting
- Prefer `[[wiki-links]]` over `[markdown](links)` for internal connections
- Use tags sparingly — too many tags reduce their utility
- Keep atomic notes focused on one idea (Zettelkasten principle)
- Always check if a note already exists before creating a duplicate
