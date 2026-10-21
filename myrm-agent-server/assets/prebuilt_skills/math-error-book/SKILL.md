---
name: math-error-book
description: >-
  Capture mistakes from math, physics, or algorithm problems into a structured
  error book in the wiki, analyze root causes, and generate spaced-repetition
  self-test papers on an Ebbinghaus schedule. Use when the user uploads or
  types a problem they got wrong, asks to review mistakes, or wants a mock
  test built from their error history.
version: 1.0.0
category: education
tags:
  - error-book
  - spaced-repetition
  - ebbinghaus
  - exam-prep
  - math
allowed-tools: file_write_tool file_read_tool web_search_tool
contract:
  steps:
    - "Phase 1: Capture — record the mistake verbatim (photo/screenshot text, user description, or typed problem) into error-book/ as one entry with frontmatter (subject, topic, error_type: careless|concept|method|blindspot, status: active|graduated, next_review date)"
    - "Phase 2: Diagnose — extract the four elements: original problem, tested knowledge point, root cause of the mistake, and the standard solution steps"
    - "Phase 3: Link — connect the entry to its concept article in the wiki concept tree (academic-subject-study); create the concept article if missing"
    - "Phase 4: Schedule — compute the next review date on the Ebbinghaus ladder (day 1, 2, 4, 7, 15, 30); write it into the entry frontmatter; offer to create a cron reminder for the due batch"
    - "Phase 5: Quiz — when entries are due, generate a self-test paper containing only the due problems (problems first, solutions on a separate section); grade the user's answers and graduate entries that pass twice in a row (status: graduated)"
  potential_traps:
    - description: "Storing only the correct answer without the user's actual wrong step"
      mitigation: "Always record the user's original wrong reasoning verbatim; the root-cause analysis depends on it"
      severity: high
    - description: "Letting graduated entries resurface in quizzes"
      mitigation: "Filter by status: active and next_review <= today when building a quiz; skip graduated entries"
      severity: medium
    - description: "Vague root-cause labels like 'not careful enough'"
      mitigation: "Map every careless label to the concrete step where the slip happened; if no concrete step exists, reclassify as concept or method"
      severity: medium
  verification_steps:
    - step_id: entry_complete
      description: "Each entry has all four elements (problem, knowledge point, root cause, standard steps) plus schedule fields"
      validation_method: "Read 3 error-book entries and confirm frontmatter fields plus all four elements are present"
    - step_id: schedule_consistent
      description: "next_review dates follow the Ebbinghaus ladder and past-due entries are surfaced"
      validation_method: "Recompute next_review from last review date for 2 entries; confirm ladder spacing (1, 2, 4, 7, 15, 30 days)"
    - step_id: quiz_scoped
      description: "Generated quizzes contain only due entries and separate problems from solutions"
      validation_method: "Inspect the generated quiz; verify every problem maps to an active entry with next_review <= today and solutions appear only in the final section"
  success_criteria: "Structured error book with diagnosed root causes and a working Ebbinghaus review loop"
  estimated_duration_seconds: 1200
---

# Math Error Book

Capture mistakes as **structured wiki entries** and run an honest
spaced-repetition loop over them.

## Entry format

Create one wiki raw article per mistake under `error-book/<subject>/`:

```markdown
---
source: "error-book"
title: "<short mistake title>"
subject: "<e.g. calculus>"
topic: "<e.g. chain rule>"
error_type: "careless | concept | method | blindspot"
status: "active | graduated"
next_review: "YYYY-MM-DD"
review_count: 0
---

## Problem
<the original problem, verbatim>

## My wrong reasoning
<the user's actual wrong step, quoted — required>

## Knowledge point tested
<the concept this problem tests; link to the concept article>

## Root cause
<careless slip at step N / concept gap / method error / blindspot — with the concrete step>

## Standard solution
<step-by-step correct solution in LaTeX>
```

## Ebbinghaus ladder

`next_review` advances 1 → 2 → 4 → 7 → 15 → 30 days after each successful
recall. A failed quiz resets the ladder and sets `review_count: 0`. Entries
that pass twice in a row on day 15+ graduate (`status: graduated`) and leave
the review pool.

## Quiz generation

When the user asks for review, collect entries with
`status: active` and `next_review <= today`, render problems first and
solutions in a separate section, grade answers, then update
`next_review` / `review_count` / `status` accordingly.
