---
name: academic-subject-study
description: >-
  Master a hard academic subject (math, physics, engineering, CS theory) by
  building a prerequisite concept tree in the wiki, running Feynman-style
  self-tests, and keeping rigorous LaTeX/KaTeX derivation records. Use when
  the user asks to learn a subject, build a concept map, prepare for exams,
  or check understanding of a specific theorem or method.
version: 1.0.0
category: education
tags:
  - academic
  - study
  - concept-tree
  - latex
  - exam-prep
allowed-tools: file_write_tool file_read_tool web_search_tool memory_save_tool
contract:
  steps:
    - "Phase 1: Scope — clarify the subject, target depth, and exam or application horizon with the user"
    - "Phase 2: Prerequisite tree — decompose the subject into a dependency-ordered concept tree (e.g. limits → continuity → derivatives → differentiation); write each concept as one wiki article under concepts/"
    - "Phase 3: Derivations — for each concept write a derivation log with rigorous LaTeX ($inline$, $$display$$) step-by-step; every non-obvious step must state the theorem or definition it applies"
    - "Phase 4: Feynman self-test — generate 3-5 plain-language questions per concept; answer them yourself first, mark gaps, and link weak spots to the error book"
    - "Phase 5: Review loop — schedule the next review point with the user and record mastery level in the concept article frontmatter (status: learning|solid|mastered)"
  potential_traps:
    - description: "Writing derivations with skipped steps the user cannot follow"
      mitigation: "Every algebraic transition must be one line per step; state the rule used above the line"
      severity: high
    - description: "Breaking KaTeX rendering with unpaired $ delimiters or stray asterisks inside math"
      mitigation: "Wrap every formula in $...$ or $$...$$; never leave a lone $ in prose; escape units outside formulas"
      severity: high
    - description: "Skipping prerequisite checks and starting from advanced topics"
      mitigation: "Probe the user on the lowest-rung concept first; if weak, build that article before moving up the tree"
      severity: medium
  verification_steps:
    - step_id: tree_rooted
      description: "Concept tree has an explicit root article listing all first-tier prerequisites"
      validation_method: "Open the root article under concepts/<subject>/ and confirm it lists every first-tier prerequisite with wiki-links"
    - step_id: latex_renders
      description: "All formulas render under KaTeX (paired delimiters, no raw errors)"
      validation_method: "Sample 3 formulas per derivation log; verify paired $...$ / $$...$$ delimiters and no lone $ in prose"
    - step_id: selftest_recorded
      description: "Feynman questions and gap marks are written into the concept articles"
      validation_method: "Open 2 concept articles and confirm self-test Q&A plus gap links to the error book exist"
  success_criteria: "Dependency-ordered concept tree in wiki with rigorous LaTeX derivations and recorded self-test gaps"
  estimated_duration_seconds: 2400
---

# Academic Subject Study

Build mastery of a hard subject as a **prerequisite-ordered concept tree** in
the wiki, with rigorous derivations and an honest self-testing loop.

## Workflow

1. **Scope** — agree with the user on the subject, target depth, and horizon
   (exam date, application goal). Record both in the root article frontmatter.
2. **Prerequisite tree** — decompose the subject into dependency-ordered
   concepts (e.g. `limits → continuity → derivatives → differentiation`).
   One wiki article per concept under `concepts/<subject>/`, linked with
   `[[wiki-links]]` to its prerequisites.
3. **Derivations** — write step-by-step derivations in LaTeX. One algebraic
   transition per line; state the theorem/definition used above the line.
   Wrap every formula in `$...$` or `$$...$$` (KaTeX-safe).
4. **Feynman self-test** — per concept, write 3–5 plain-language questions,
   answer them yourself, and mark gaps with `> [!gap]` callouts. Link gaps to
   the matching `math-error-book` entry when the gap produced a mistake.
5. **Review loop** — record `status: learning | solid | mastered` and the next
   review date in each concept article's frontmatter; suggest the next review
   point to the user.

## Output conventions

- Root article: `concepts/<subject>/_index.md` with the full tree and mastery
  overview.
- Concept article frontmatter: `subject`, `prerequisites` (list),
  `status`, `next_review`.
- All math in paired `$`/`$$` delimiters; never leave a lone `$` in prose.
