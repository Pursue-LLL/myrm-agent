---
name: expert-persona-distiller
description: >-
  Extract, distill, and package unstructured expert text corpora (interview transcripts,
  articles, Q&A logs, architecture reviews) into fully interactive, conversational Persona Skill
  presets. Generates self-contained SKILL.md bundles with 5-dimensional cognitive modeling,
  expert decision heuristics, domain lexicon, and few-shot golden dialogs.
version: 1.0.0
category: creative
tags:
  - persona
  - corpus-distillation
  - expert-modeling
  - conversational-skill
  - cognitive-framework
  - knowledge-engineering
  - 人设蒸馏
  - 专家模型
  - 对话技能
  - 语料提炼
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Ingest & Corpus Validation — check source texts against minimum volume (>= 500 words) and diversity of perspectives"
    - "Phase 2: 5-Dimensional Cognitive Modeling — extract Cognitive Frameworks, Domain Lexicon, Conversational Stance, Decision Heuristics, and Hard Boundaries"
    - "Phase 3: Golden Dialogue Synthesis — construct 2-3 high-fidelity multi-turn Q&A dialogues demonstrating authentic reasoning chains"
    - "Phase 4: Skill Preset Packaging — assemble and output a production-ready, self-contained SKILL.md for the target persona"
  potential_traps:
    - description: "Superficial tone mimicking without capturing the expert's foundational decision-making logic"
      mitigation: "Mandatory extraction of Dimension 4 (Decision Heuristics) with explicit trade-off reasoning"
      severity: high
    - description: "Unbounded hallucination on questions outside the corpus domain"
      mitigation: "Strict Dimension 5 (Hard Negative Boundaries) defining explicit out-of-scope refusal behavior"
      severity: high
    - description: "Overly verbose system prompt causing downstream model instruction drift"
      mitigation: "Enforce concise rule density with structured markdown tables and high-signal few-shot pairs"
      severity: medium
  verification_steps:
    - step_id: corpus_density_checked
      description: "Verify input text contains sufficient reasoning evidence"
      validation_method: "Length and semantic diversity validation"
      is_required: true
    - step_id: skill_preset_generated
      description: "Produce valid SKILL.md containing frontmatter, system prompt, and golden dialogs"
      validation_method: "file_write_tool succeeds at target path"
      is_required: true
  success_criteria: "Generates a fully-formed, executable conversational Persona SKILL.md that faithfully mirrors the expert's reasoning, tone, and refusal boundaries"
  estimated_duration_seconds: 300
---

# Expert Persona Corpus Distillation & Conversational Skill Preset Builder

## Overview

The `expert-persona-distiller` skill transforms raw, unstructured expert materials—such as
interview transcripts, technical blog posts, Q&A logs, voice memo summaries, or architectural design
reviews—into a **fully interactive, conversational Persona Skill**.

While general style extractors focus solely on surface copywriting quirks, `expert-persona-distiller`
reconstructs the expert's internal **mental reasoning models, domain terminology, conversation posture,
and hard ethical/scope boundaries**, packaging them into a ready-to-mount Myrm Skill.

## The 5-Dimensional Cognitive Persona Matrix

When analyzing expert corpora, systematically extract and document the following five core dimensions:

| Dimension | Focus Area | Key Extraction Indicators |
| --- | --- | --- |
| **1. Cognitive Frameworks & Mental Models** (认知框架与思维模型) | How the expert deconstructs problems | First-principles decomposition, MECE structuring, Pareto distribution, inverted risk analysis, systemic leverage points. |
| **2. Domain Lexicon & Jargon** (行业术语与习惯用语) | Specific technical vocabulary & metaphors | Unique idioms, shorthand notations, proprietary frameworks, preferred vs. avoided industry terms. |
| **3. Conversational Stance & Tone** (对话姿态与语气调性) | Interpersonal dynamics & emotional posture | Pragmatic realism, Socratic questioning, high information density, direct constructive criticism, empathetic mentoring. |
| **4. Decision Heuristics & Trade-offs** (决策启发式与权衡逻辑) | How the expert makes choices under uncertainty | Default biases (e.g., "always bias towards simplicity"), explicit cost-benefit equations, risk tolerances, prioritization rules. |
| **5. Hard Boundaries & Refusal Guardrails** (绝对禁忌与边界防线) | What the expert will never say or do | Honest admission of unknown facts, refusal to speculate outside domain, rejection of superficial vanity metrics or hype. |

## End-to-End Distillation SOP

### Phase 1: Corpus Ingestion & Density Audit
1. Ingest representative texts (interview logs, chat transcripts, articles, or meeting minutes).
2. Ensure minimum analytical mass: at least 500 words of authentic expert discourse showing both problem diagnosis and reasoning.
3. If corpus lacks depth in certain domains, surface 1–2 clarifying questions to capture missing stances.

### Phase 2: Matrix Extraction & Reasoning Distillation
1. Identify the expert's primary thinking archetypes (e.g., Systems Architect, Quantitative Strategist, Pragmatic Operator).
2. Synthesize concrete heuristics in the format: `When faced with [X], prefer [A] over [B] because [C]`.
3. Capture exact verbatim catchphrases and characteristic cadence.

### Phase 3: Golden Dialogue Synthesis
Construct 2–3 multi-turn "Golden Dialogues" (金牌对答范式) demonstrating:
- **Direct Inquiry**: Addressing a core domain technical question with characteristic depth.
- **Ambiguous Request**: Pushing back on vague premises, asking counter-questions, and reframing the problem.
- **Edge / Out-of-Scope Inquiry**: Exercising Dimension 5 guardrails gracefully without robotic apologies.

### Phase 4: Self-Contained SKILL.md Assembly
Output the final skill artifact directly to:
`assets/prebuilt_skills/persona-{slug}/SKILL.md` (or the user-designated workspace directory).

The generated `SKILL.md` must follow standard Myrm prebuilt skill structure:
- Valid YAML Frontmatter with name, description, tags (`persona`, `conversational`, `expert-model`), and allowed tools.
- Role definition and persona background.
- Operationalized behavioral directives.
- Golden Few-shot dialogues.

## Quality Checklist

Before finalizing the distilled persona skill:
- [ ] Does the persona exhibit distinct reasoning patterns, not just generic polite assistant behavior?
- [ ] Are decision heuristics specific and actionable with clear trade-off preferences?
- [ ] Are hard negative boundaries defined to prevent out-of-domain hallucinations?
- [ ] Are the Golden Dialogues realistic, multi-turn, and demonstrating typical vocabulary?
- [ ] Is the generated SKILL.md completely self-contained and free of broken external links?
