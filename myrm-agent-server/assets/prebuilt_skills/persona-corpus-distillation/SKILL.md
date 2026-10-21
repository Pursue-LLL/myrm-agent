---
name: persona-corpus-distillation
description: >-
  Extract, distill, and synthesize authentic expert conversational persona skills from raw dialogue history,
  interview transcripts, consultation records, and multi-turn chat archives. Produces a production-ready,
  bounded Myrm SKILL.md package with domain mental models, voice fingerprint, golden few-shot playbooks,
  and anti-hallucination refusal boundaries.
version: 1.0.0
category: creative
tags:
  - persona
  - corpus-distillation
  - conversational-skill
  - expert-agent
  - voice-fingerprint
  - few-shot-playbook
  - prompt-engineering
  - 人设蒸馏
  - 专家对话技能
  - 语料提炼
license: MIT
allowed-tools: file_read_tool file_write_tool memory_save_tool memory_search_tool
contract:
  steps:
    - "Phase 1: Ingestion & PII Redaction — scan raw multi-turn dialogue archives, redact sensitive PII (phones, credentials, real names if needed), and normalize turn boundaries"
    - "Phase 2: Domain Mental Model Extraction — extract core decision heuristics, domain taxonomy, proprietary frameworks, and recurring problem-solving formulas"
    - "Phase 3: Conversational Voice Fingerprint Profiling — capture tone of voice, sentence pacing, habitual openers/closers, empathy index, and skepticism/directness posture"
    - "Phase 4: Golden Few-Shot Scenario Synthesis — distill 3-5 authentic golden Q&A dialogues representing core scenarios, edge questions, and out-of-scope refusals"
    - "Phase 5: Self-Contained SKILL.md Packaging — assemble a complete, compliant Myrm skill markdown artifact with frontmatter, execution contract, and anti-hallucination guardrails"
  potential_traps:
    - description: "Hallucinating personal traits or domain facts not supported by the input corpus"
      mitigation: "Strict corpus grounding rule: every distilled principle and vocabulary item must cite at least one representative turn or snippet from the source text"
      severity: high
    - description: "Leaking raw PII or proprietary sensitive credentials into the generated SKILL.md"
      mitigation: "Automated PII scrub: mask phone numbers, email addresses, internal IP addresses, API tokens, and real client identifiers"
      severity: high
    - description: "Overly broad persona causing out-of-domain hallucinations"
      mitigation: "Mandatory Boundary & Refusal section specifying topics the persona must explicitly decline or redirect"
      severity: medium
  verification_steps:
    - step_id: corpus_grounding_verified
      description: "Ensure mental models and voice traits directly reference source corpus fragments"
      validation_method: "Verify each extracted trait has corresponding verbatim quotes or frequency evidence"
      is_required: true
    - step_id: pii_clean_verified
      description: "Verify absence of phone numbers, emails, and credentials in the output skill"
      validation_method: "Regex pattern scan for PII tokens"
      is_required: true
    - step_id: skill_contract_compliant
      description: "Verify generated SKILL.md contains valid YAML frontmatter, 5 core sections, and refusal guardrails"
      validation_method: "Validate against Myrm SKILL specification schema"
      is_required: true
  success_criteria: "A self-contained, high-fidelity expert conversational SKILL.md that can be directly registered in Myrm SkillStore or injected into an Agent's system prompt"
  estimated_duration_seconds: 480
---

# Persona Corpus Distillation & Conversational Skill Synthesis

## Overview

Handcrafted persona prompts often sound generic, mechanical, and lack authentic domain depth.
`persona-corpus-distillation` solves this by taking raw dialogue histories (chat logs, consultation recordings,
expert Q&A transcripts, email threads) and distilling them into a high-fidelity, production-grade conversational
skill (`SKILL.md`) that captures the persona's authentic voice, mental models, and operational boundaries.

---

## The 5-Phase Distillation Pipeline

```
Raw Dialogue Corpus (Chat logs / Interviews / Q&A archives)
                     │
    [Phase 1] ───────▼──────── [PII Redaction & Turn Normalization]
                     │
    [Phase 2] ───────▼──────── [Domain Mental Models & Taxonomy]
                     │
    [Phase 3] ───────▼──────── [Conversational Voice Fingerprint]
                     │
    [Phase 4] ───────▼──────── [Golden Few-Shot Playbook Synthesis]
                     │
    [Phase 5] ───────▼──────── [Production SKILL.md Packaging]
```

### Phase 1: Ingestion & PII Redaction
1. **Turn Normalization**: Parse conversational boundaries (`User: ... / Expert: ...`).
2. **PII Redaction**:
   - Mask mobile phone numbers -> `[PHONE_REDACTED]`
   - Mask email addresses -> `[EMAIL_REDACTED]`
   - Mask internal URLs, passwords, API tokens -> `[SECRET_REDACTED]`
   - Replace private company / customer names with anonymized placeholders if requested.

### Phase 2: Domain Mental Models & Taxonomy
Extract the expert's foundational worldview and operational principles across the core cognitive pillars:
1. **Decision Heuristics**: What rules of thumb does the expert repeatedly invoke when evaluating trade-offs?
2. **Mental Models**: Foundational principles and analytical frameworks (e.g., First Principles, Inversion, Pareto Distribution, Defensive Systems) governing the expert's reasoning.
3. **Conversational Dynamics**: Pacing, turn-taking patterns, question-asking cadence, and empathetic tone transitions.
4. **Negative Guardrails & Anti-Patterns**: Strict taboos, forbidden advice, sycophantic praise avoidance, and phrases the persona NEVER utters.
5. **Proprietary Terminology**: Unique vocabulary, abbreviations, or mental models specific to this expert.
6. **Problem-Solving Sequence**: How does the expert diagnose problems? (e.g., first principles vs. pattern matching vs. hypothesis-driven).

### Phase 3: Conversational Voice Fingerprint
Systematically profile the expert's interpersonal communication style:
1. **Sentence Length & Pacing**: Short punchy staccato vs. structured multi-paragraph expositions.
2. **Tone & Attitude**: Warm mentor, sharp pragmatist, academic researcher, or street-smart operator.
3. **Habitual Markers**: Catchphrases, rhetorical questions, characteristic transitions.
4. **Empathy & Candor**: How does the expert deliver tough feedback or validate user pain points?

### Phase 4: Golden Few-Shot Playbook Synthesis
Synthesize 3-5 authentic conversational pairs:
1. **Standard In-Domain Consultation**: Demonstrates core expertise and typical diagnostic depth.
2. **Vague or Misguided User Inquiry**: Demonstrates how the expert redirects misconceptions and asks clarifying questions.
3. **Challenging / Edge Scenario**: Demonstrates nuanced trade-off analysis under constraints.
4. **Out-of-Scope / Boundary Refusal**: Demonstrates how the expert politely but firmly refuses unrelated or unsafe requests.

### Phase 5: Self-Contained SKILL.md Packaging & Dual Deliverables
Assemble the distilled knowledge into dual deliverables compliant with Myrm Skill and Agent Persona specifications:
1. **`persona-spec.yaml`**: Machine-readable configuration defining the cognitive profile, 3D tone parameters (Formality, Directness, Humor), decision rules, and trigger keywords.
2. **`SKILL.md`**: Standalone, human-auditable and model-consumable Markdown package featuring:
   - Standard YAML frontmatter (`name`, `description`, `version`, `category: conversational`, `contract`).
   - Role definition and system persona instructions.
   - Core knowledge and mental models matrix.
   - Voice guidelines and Negative Guardrails (forbidden communication patterns / anti-patterns).
   - Golden Few-Shot Q&A dialogue blocks.
   - Explicit scope boundaries, fallback responses, and the **Quality Gate Checklist**.

---

## Anti-Hallucination & Safety Guardrails

1. **Evidence-Based Extraction**: Never invent backstory or opinions absent from the raw corpus.
2. **Clear Boundary Gating**: Every distilled persona must explicitly refuse queries outside its proven domain competence.
3. **Zero Token Leakage**: Distilled skills must not echo raw unprocessed conversation chunks that could reveal proprietary corporate secrets.
