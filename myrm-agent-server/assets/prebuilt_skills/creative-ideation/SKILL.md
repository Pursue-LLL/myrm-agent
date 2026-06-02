---
name: creative-ideation
description: >-
  Structured brainstorming and creative ideation framework. Generates diverse ideas
  using multiple thinking techniques, then evaluates and refines the best candidates.
  No external tools required — pure reasoning skill.
version: 1.0.0
category: creative
tags:
  - brainstorming
  - ideation
  - creativity
  - strategy
  - innovation
allowed-tools: file_write_tool memory_save
contract:
  steps:
    - "Phase 1: Frame — define the creative challenge and constraints"
    - "Phase 2: Diverge — generate 20+ ideas using multiple techniques"
    - "Phase 3: Cluster — group ideas by theme and identify patterns"
    - "Phase 4: Converge — evaluate, rank, and refine top candidates"
  potential_traps:
    - description: "Converging too early on the first decent idea"
      mitigation: "Force at least 20 raw ideas before any evaluation"
      severity: high
    - description: "All ideas clustering around the same obvious solution"
      mitigation: "Apply at least 3 different thinking techniques (reversal, analogy, constraint removal)"
      severity: medium
  success_criteria: "A ranked shortlist of 3-5 creative, feasible ideas with clear next steps"
  estimated_duration_seconds: 900
---

# Creative Ideation

## Overview

Great ideas rarely come from a single brainstorming pass. This skill enforces structured divergent-then-convergent thinking to produce genuinely creative solutions.

**Core principle:** Quantity breeds quality. Generate many before selecting few.

## Phase 1: Frame the Challenge

Before generating ideas, establish a clear creative brief:

1. **What's the problem or opportunity?** — State it in one sentence
2. **Who is it for?** — Target audience or user
3. **What are the constraints?** — Budget, timeline, technology, brand, legal
4. **What does success look like?** — Measurable outcomes
5. **What's been tried before?** — Avoid reinventing failed approaches

Reframe the challenge as "How might we..." (HMW) to open up solution space.

## Phase 2: Diverge — Generate Ideas

Use at least 3 of these techniques to ensure diverse thinking:

### Technique 1: First Principles
Strip the problem to its fundamentals. What's the underlying need? What if we rebuilt from scratch?

### Technique 2: Reversal
What's the opposite of the obvious solution? What if we made the problem worse on purpose — what would that look like?

### Technique 3: Analogy Transfer
How do other industries solve similar problems? (Nature, gaming, hospitality, military, etc.)

### Technique 4: Constraint Removal
What would we do with unlimited budget? Zero time pressure? No regulatory limits? Then work backwards.

### Technique 5: Random Entry
Pick a random word or image. How could it connect to the problem?

### Technique 6: Audience Swap
How would a child solve this? A retired engineer? A competitor? Someone from a completely different culture?

### Output Format
Number all ideas sequentially. Each idea gets one line — no evaluation yet.

## Phase 3: Cluster and Pattern

1. Group related ideas into 4-6 themes
2. Name each cluster
3. Identify cross-cluster combinations — often the best ideas are hybrids
4. Note any surprising patterns or blind spots

## Phase 4: Converge — Evaluate and Refine

Score each top candidate on:

| Criterion | Weight | Scale |
|-----------|--------|-------|
| Impact — how much does it move the needle? | 30% | 1-5 |
| Feasibility — can we actually build/do this? | 25% | 1-5 |
| Novelty — is this genuinely different? | 25% | 1-5 |
| Speed — how fast can we validate? | 20% | 1-5 |

### Final Deliverable

For each top-3 idea:
- **Name** — memorable, descriptive title
- **One-liner** — what it is in plain language
- **Why it could work** — key insight or advantage
- **Biggest risk** — what could go wrong
- **Next step** — the smallest action to validate it
