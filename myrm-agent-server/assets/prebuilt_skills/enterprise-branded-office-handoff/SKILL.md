---
name: enterprise-branded-office-handoff
description: >-
  Enterprise-grade SOP and packaging wizard to deconstruct proprietary Office templates
  (PPTX, DOCX, XLSX), encapsulate them into self-contained, zero-dependency skill packs,
  and execute seamless, configuration-free handoffs to colleagues.
version: 1.0.0
category: office
tags:
  - office
  - enterprise-templates
  - brand-vi
  - colleague-handoff
  - pptx
  - docx
  - xlsx
  - 企业模板
  - 同事交接
  - 免配置
license: MIT
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool file_edit_tool
contract:
  steps:
    - 1. Deconstruct proprietary Office template assets into tokens, layout schemas, and compliance rules
    - 2. Package assets into a standard self-contained skill structure with Python sandbox generators
    - 3. Generate colleague handoff manifest with one-click verification and smoke prompts
    - 4. Output handoff checklist and verify zero host-dependency execution
  potential_traps:
    - Hardcoding absolute local file paths into the skill package
    - Requiring colleagues to install host Office software or system fonts
    - Omitting brand VI color codes or thesis headline guidelines
    - Failing to sanitize confidential company data from the sample templates
  verification_steps:
    - Confirm the packaged skill generates standard Office deliverables in a clean sandbox
    - Verify handoff manifest includes copy-paste ready starter prompts
    - Validate that generated documents conform to anti-wall-of-text and thesis statement rules
  success_criteria:
    - Zero host-software configuration needed for receiving colleagues
    - High-fidelity preservation of corporate colors, typography, and layout standards
    - Complete self-contained asset bundle with automated smoke test instructions
---

# Enterprise Branded Office Skill Pack & Colleague Handoff

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


Transform enterprise-specific Office templates (presentations, reports, financial models) into self-contained, zero-configuration Myrm Skill Packs that can be effortlessly handed off to team members.

## Why This Matters

Enterprises invest heavily in polished PowerPoint slide decks, Word corporate report templates, and standardized Excel sheets. However, sharing these assets with colleagues often leads to:
1. Broken layouts, missing fonts, and brand identity drift across different computers.
2. Repetitive manual prompt engineering to enforce corporate guidelines (e.g., color hexes, margins, logo safe zones).
3. Complex environment dependencies (requiring specific local Microsoft Office versions or custom macros).

This skill provides a standardized 3-phase methodology to convert raw Office templates into robust, versioned, and instantly shareable AI Skill Packs.

---

## The 3-Phase Handoff Methodology

### Phase 1: Asset Deconstruction (解构)
Analyze the source corporate template and extract its core structural parameters:
- **Design Tokens**:
  - Primary, secondary, and accent colors in HEX and RGB format (e.g., `BrandBlue: #003366`, `AccentGold: #D4AF37`).
  - Font hierarchies: Title, Body, Code, and Fallback system fonts.
  - Page dimensions & grids: 16:9 widescreen slides, A4 document margins, standard column widths.
  - Logo placement rules and safe margin boundaries.
- **Structural Blueprint**:
  - Slide masters / page header-footer templates.
  - Content density constraints (maximum 4 bullet points per block, maximum 25 Chinese characters or 15 English words per line).
  - Thesis Headline requirements: Every slide/section must have an assertion-driven headline.

### Phase 2: Skill Encapsulation (封装)
Organize the deconstructed rules into a self-contained Skill Pack directory structure:

```text
custom-enterprise-office-pack/
├── SKILL.md                  # Complete LLM instructions and quality gates
├── assets/
│   ├── tokens.json           # Machine-readable color, font, and spacing tokens
│   └── sanitized_sample.pptx # Desensitized base template (no private company data)
├── scripts/
│   └── generate_office.py    # Zero-dependency Python script using python-pptx / docx / openpyxl
├── rules/
│   └── quality_gates.md      # Anti-wall-of-text, thesis statement, and layout rules
└── handoff_manifest.yaml     # Colleague onboarding guide, smoke prompts, and manifest
```

#### Standard `handoff_manifest.yaml` Specification:
```yaml
pack_name: "acme-corp-branded-slides"
version: "1.0.0"
target_scenarios:
  - "Quarterly Business Review (QBR)"
  - "Product Launch Keynotes"
  - "Executive Briefings"
prerequisites:
  host_software: "None (runs entirely in sandboxed Python)"
  system_fonts: "Standard system fallbacks configured"
smoke_test_prompt: "按照 Acme 品牌规范制作一份关于 Q3 战略复盘的 3 页汇报 PPT，包含封面、核心业务结论、下一步计划。"
handoff_contact: "Platform & Enablement Team"
```

### Phase 3: Zero-Config Colleague Handoff (交接)
When delivering the packaged skill to a coworker:
1. **Sanitization Check**: Ensure all test numbers, confidential client names, and proprietary credentials in the sample assets are replaced with realistic dummy data.
2. **One-Click Handoff Summary Card**: Present the colleague with a clean, actionable transfer card containing:
   - What the pack does and what scenarios it covers.
   - Ready-to-use prompt templates for immediate use.
   - Clear instructions on how to invoke the skill without adjusting system settings.
3. **Automated Smoke Test Verification**: Instruct the receiving colleague to run the smoke test prompt. Verify that the generated `.pptx`, `.docx`, or `.xlsx` document passes all visual inspections and corporate compliance gates.

---

## Integration with Myrm Ecosystem

- **Upstream Input**: Consumes extracted design parameters from `brand-vi-guidelines` (Topic 08 #10).
- **Core Engine**: Complements `office-document` with organization-specific templates and constraints.
- **Quality Gates**: Enforces `PptReportingPlanOutlineQualityGate` (Topic 08 #11) to eliminate pure-noun titles and walls of text.
- **Continuous Learning**: Employs `SkillPackEmbeddedExperienceLibraryLoop` (Topic 08 #12) to record feedback and recurring edge cases in the pack's `learnings.md`.
