---
name: enterprise-governance
description: >-
  Synthesize, enforce, and audit enterprise governance policies across four core pillars:
  Brand Tone of Voice, Data Security & Confidentiality Classification (L1-L4),
  Legal & Contract Compliance, and AI Safe SDLC Guardrails. Ingests corporate policy
  manuals and outputs machine-auditable policy rules, pre-flight review checklists,
  and hard-gate verification matrices.
version: 1.0.0
category: enterprise-ops
tags:
  - governance
  - compliance
  - data-security
  - brand-voice
  - policy-synthesizer
  - safe-sdlc
  - 企业治理
  - 合规质检
  - 数据安全
allowed-tools: file_read_tool file_write_tool bash_code_execute_tool
contract:
  steps:
    - "Phase 1: Corporate Policy Ingestion & Governance Scope Triage — Parse handbook/rules into 4 core governance pillars"
    - "Phase 2: Data Classification & Confidentiality Gating — Tag data assets into L1 (Public) to L4 (Strictly Confidential); enforce DLP"
    - "Phase 3: Brand Tone & Legal Compliance Rule Extraction — Formalize prohibited terminology, mandatory disclaimer clauses, and voice guidelines"
    - "Phase 4: Machine-Auditable Policy Synthesis & CI/Agent Gate Export — Generate automated lint rules, pre-flight checklists, and YAML governance policies"
  potential_traps:
    - description: "Defining vague qualitative governance rules that an automated agent cannot verify or enforce"
      mitigation: "Every rule must be operationalized into explicit regex patterns, prohibited wordlists, or boolean assertions"
      severity: critical
    - description: "Applying heavy L4 confidential restrictions indiscriminately across all internal documents"
      mitigation: "Strict proportionality: enforce L4 boundaries only on PII, financials, credentials, and trade secrets"
      severity: high
    - description: "Missing mandatory legal disclaimers on financial, medical, or contractual AI outputs"
      mitigation: "Inject automated disclaimer appending gates for all regulated domain deliverables"
      severity: high
  verification_steps:
    - step_id: governance_contract_complete
      description: "Ensure the generated policy document covers all 4 pillars with actionable rules and verification steps"
      validation_method: "Inspect output markdown for all mandatory pillar sections and verification matrices"
      is_required: true
    - step_id: machine_auditable_rules_valid
      description: "Verify that exported governance configuration files (YAML/JSON) parse successfully"
      validation_method: "Syntax check on generated rule files"
      is_required: true
  success_criteria: "A formal enterprise governance specification and machine-executable audit rules are generated, guaranteeing zero compliance slips."
  estimated_duration_seconds: 300
---

# Enterprise Governance Skill Template Pack & Policy Synthesizer

## Overview

In enterprise environments, AI agents operating without governance risk brand dilution, privacy breaches, regulatory non-compliance, and severe legal liability. The Anthropic Applied AI *AI-Native SDLC Playbook* highlights that true enterprise readiness requires formalizing governance from day zero.

The **Enterprise Governance Policy Synthesizer** ingests corporate policies, employee handbooks, and compliance standards, transforming them into:
1. **The 4-Pillar Governance Specification** (Human-readable SSOT).
2. **Automated Machine Linting Rules** (Enforced by agents before any external artifact delivery).
3. **Audit Trails & Incident Triage Checklists**.

---

## The 4 Core Governance Pillars

### Pillar 1: Brand Voice & Communications Tone
- **Tone Matrix**: Professional, assertive, constructive, customer-first.
- **Terminology Governance**: Mandatory brand naming conventions, deprecated vocabulary lists, and tone consistency guidelines.
- **Negative Invariants**: Anti-text-wall, anti-cliché, no false modesty or exaggerated marketing buzzwords.

### Pillar 2: Data Security & Confidentiality Classification (L1 - L4)
| Level | Classification | Examples | Allowed Agent Tools / Exposure |
| --- | --- | --- | --- |
| **L1** | Public | Marketing blogs, press releases | Web search, external browsing, public repos |
| **L2** | Internal Use | Internal wikis, team notes, tickets | Local workspace read/write, internal MCPs |
| **L3** | Confidential | Roadmaps, customer contracts, code | Sandboxed execution only; strictly NO external uploads |
| **L4** | Restricted / PII | Passwords, API keys, payroll, SSN | Zero LLM retention; redactor tool mandatory before inference |

### Pillar 3: Legal & Regulatory Compliance
- **Contractual Guarantees**: Absolute prohibition on committing delivery dates or legal liability without Human-in-the-Loop approval.
- **Regulatory Disclaimers**: Automatic injection of statutory notices for financial projections, tax calculations, or medical recommendations.
- **Copyright & License Audits**: Automatic verification that generated software components adhere to approved open-source licenses (MIT/Apache vs GPL).

### Pillar 4: AI-Native Safe SDLC Guardrails
- **Pre-Commit Security Checks**: Automatic scan for hardcoded secrets, shell-injection vulnerabilities, and unsanitized inputs.
- **Physical Evidence Requirement**: No PR, feature, or bugfix claim is accepted without passing automated unit/integration test evidence.
- **Non-Destructive Git Discipline**: Hard ban on `git reset --hard`, destructive rebases, or force-pushes in agent workflows.

---

## Machine-Auditable Policy Output Format

Every synthesized governance bundle generates a machine-readable specification (`governance_rules.yaml`):

```yaml
version: "1.0.0"
governance_policy:
  dlp:
    block_pii: true
    block_credentials: true
    allowed_domains:
      - "internal.myrmidon.ai"
  brand:
    banned_words:
      - "disruptive"
      - "synergize"
      - "guaranteed profit"
  legal:
    hitl_required_on_commitments: true
    mandatory_disclaimer: "Confidential & Proprietary. All estimates subject to formal contractual execution."
```
