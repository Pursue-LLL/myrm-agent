---
name: persona-voice
description: >-
  Extract, distill, and continuously adapt personalized writing voice profiles (Tone of Voice)
  from user sample writings. Injects authentic author persona, tone, pacing, vocabulary preferences,
  and negative constraints into downstream writing and distribution pipelines.
version: 1.0.0
category: creative
tags:
  - voice
  - persona
  - tone-of-voice
  - writing-style
  - personalization
  - adaptive-learning
  - copywriting
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Ingest & Gate — validate sample texts against length threshold and multi-style scope"
    - "Phase 2: Distill — extract 5-dimensional voice matrix (Lexical, Syntactic, Tonal, Formatting, Negative)"
    - "Phase 3: Standardize — generate structured `personal_voice.md` specification"
    - "Phase 4: Persist & Sync — save voice profile to Memory and downstream writing skill registry"
  potential_traps:
    - description: "Sample text too short or unrepresentative leading to hallucinated style rules"
      mitigation: "Enforce sample length gate (>=300 words) and interactive clarifying questions"
      severity: high
    - description: "Overly extreme style rules compromising factual accuracy or readability"
      mitigation: "Include readability baselines and explicit factual integrity constraints"
      severity: medium
  success_criteria: "Structured, human-readable 5-dimensional Tone of Voice specification saved to Memory and ready for downstream writing pipelines"
  estimated_duration_seconds: 600
---

# Persona Voice & Continuous Adaptation Skill

## Overview

General AI text humanizers remove robotic artifacts, but `persona-voice` gives content a distinct human soul. This skill analyzes an author's past sample works, systematically extracts their unique writing DNA across five dimensions, and persists an adaptable Tone of Voice profile.

## Five-Dimensional Voice Matrix

Every personal voice profile must strictly follow the schema defined in `references/tone-of-voice-spec.md`:

1. **Syntactic Pacing (句式与节奏)**: Sentence length distribution, fragment usage, transition density, rhetorical questions.
2. **Lexical Palette (词汇偏好与黑名单)**: High-frequency characteristic terms, forbidden buzzwords/corporate jargon, domain terminology.
3. **Tonal & Rhetorical Attitude (修辞与态度)**: Formality level, humor/irony stance, self-referential posture (first-person vs detached observer), emotional temperature.
4. **Formatting & Punctuation (排版与标点习惯)**: Exclamation/dash habits, bullet vs narrative preference, whitespace density, emoji stance.
5. **Negative Constraints (绝对禁忌模式)**: Banned AI transition tropes ("In today's fast-paced world", "Furthermore", "It is worth noting"), cliché conclusions.

## Execution SOP

When extracting or updating a voice profile, follow `references/extraction-sop.md`:

- **Extraction Mode**: Parse 1–3 representative writing samples (>= 300 words).
- **Interactive Refinement**: If samples are scarce, trigger targeted interactive discovery questions.
- **Persistence Protocol**: Persist using `memory_save_tool` with key `persona_voice:<voice_id>` for seamless multi-profile switching.
- **Adaptive Flywheel**: When human edits on generated artifacts are detected, parse the diff and update the active voice matrix.

## Reference Specifications

- `references/tone-of-voice-spec.md` — 5-dimensional schema & output markdown template
- `references/extraction-sop.md` — Ingestion gate, multi-persona isolation, and diff-based adaptation SOP
