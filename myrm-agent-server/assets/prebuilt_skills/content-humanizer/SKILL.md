---
name: content-humanizer
description: >-
  Transform AI-generated text into natural, human-sounding writing. Eliminates
  common AI patterns, injects authentic voice, and preserves meaning while making
  content indistinguishable from human writing.
version: 1.0.0
category: creative
tags:
  - writing
  - humanize
  - content
  - copywriting
  - editing
allowed-tools: file_write_tool file_read_tool
contract:
  steps:
    - "Phase 1: Analyze — identify AI patterns in the source text"
    - "Phase 2: Voice — establish the target human voice and style"
    - "Phase 3: Rewrite — transform section by section"
    - "Phase 4: Polish — final pass for naturalness and flow"
  potential_traps:
    - description: "Over-correcting into overly casual or sloppy writing"
      mitigation: "Match the formality level to the content type and audience"
      severity: medium
    - description: "Losing key information while restructuring"
      mitigation: "Cross-check rewritten version against source for completeness"
      severity: high
  success_criteria: "Output reads naturally, retains all key information, and passes AI detection scrutiny"
  estimated_duration_seconds: 600
---

# Content Humanizer

## Overview

AI-generated text has telltale patterns that informed readers recognize instantly. This skill systematically identifies and eliminates those patterns while preserving the content's meaning and structure.

## Phase 1: Detect AI Patterns

Scan the source text for these common signals:

### Structural Patterns
- Excessive parallelism (every paragraph follows the same structure)
- Predictable topic-sentence → evidence → conclusion format
- Over-use of transition words ("Furthermore", "Moreover", "Additionally")
- Lists where every item is the same length

### Lexical Patterns
- Hedging language ("It's important to note", "It's worth mentioning")
- Filler qualifiers ("In today's fast-paced world", "In the realm of")
- Overuse of superlatives ("comprehensive", "robust", "seamless")
- Perfect synonym cycling (never repeating a word)

### Tonal Patterns
- Uniformly positive or neutral tone (no genuine frustration or humor)
- Explaining things the reader obviously knows
- Overly balanced "on the other hand" arguments
- Closing with a generic call-to-action

## Phase 2: Establish Target Voice

Ask or infer:
1. **Who is the author?** — Their expertise, personality, perspective
2. **Who reads this?** — Audience sophistication and expectations
3. **What's the medium?** — Blog post, email, report, social media, documentation
4. **What's the tone?** — Professional, conversational, authoritative, playful

### Voice Dimensions

| Dimension | AI Default | Human Fix |
|-----------|-----------|-----------|
| Sentence length | Uniform medium | Varied (short punchy + long flowing) |
| Paragraph length | 3-4 sentences each | Varied (one-liners mixed with longer blocks) |
| Confidence | Hedged everything | Confident claims with selective hedging |
| Specificity | Generic examples | Concrete, specific details |
| Emotion | Neutral | Appropriate frustration, excitement, humor |

## Phase 3: Rewrite

Work section by section:

1. **Vary sentence structure** — Mix short declarative sentences with longer ones. Start some with conjunctions. Use fragments intentionally.

2. **Replace AI vocabulary** — Swap overused words:
   - "utilize" → "use"
   - "leverage" → "use" or just describe the action
   - "comprehensive" → describe what's actually covered
   - "robust" → describe why it's reliable
   - "seamless" → describe the actual experience

3. **Add human texture**:
   - Personal asides ("I've seen this go wrong when...")
   - Specific examples instead of generic ones
   - Admitted limitations ("This won't work if...")
   - Occasional informal language where appropriate

4. **Fix transitions** — Remove mechanical connectors. Let ideas flow naturally. Use callbacks to earlier points instead of "As mentioned previously."

5. **Restructure for surprise** — Don't always lead with the topic sentence. Sometimes start with an example, a question, or a contrarian claim.

## Phase 4: Polish

Final naturalness check:

- [ ] Read aloud — does it sound like someone talking?
- [ ] No two consecutive paragraphs start the same way
- [ ] At least one moment of genuine personality (humor, opinion, frustration)
- [ ] Specific numbers or examples replace vague claims
- [ ] The piece has a distinct point of view, not just information
