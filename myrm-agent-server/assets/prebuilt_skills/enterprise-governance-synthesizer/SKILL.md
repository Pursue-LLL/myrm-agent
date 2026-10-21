---
name: enterprise-governance-synthesizer
description: "Synthesize, extract, audit, and compile enterprise governance guidelines (brand voice tone, data security classification, and legal compliance boundaries) into executable agent policy constraints."
version: "1.0.0"
category: "governance"
tags:
  - enterprise-governance
  - compliance
  - policy
  - brand-voice
  - security-classification
  - legal-boundaries
allowed-tools:
  - file_read_tool
  - file_write_tool
---

# Enterprise Governance Policy Synthesizer Skill (企业治理规范与合规约束编译器技能)

## Overview

A dedicated skill for translating dense corporate handbooks, employee codes of conduct, privacy policies, and regulatory mandates into machine-executable **Enterprise Governance Policy Packs (`governance-policy.yaml`)**.

It bridges the gap between legal/compliance requirements and AI execution, ensuring that all agents operating across the company respect data classification boundaries, corporate tone, and legal redlines without human micro-management.

---

## 4 Core Governance Pillars (企业治理四大支柱)

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Brand Tone & Voice Boundaries (品牌声调与对外口径)        │
│    ├── Prohibited phrasing, tone of voice, crisis responses │
│    └── Official positioning statements and terminology      │
├─────────────────────────────────────────────────────────────┤
│ 2. Data Security & Classification (数据安全与分类分级)      │
│    ├── Tier 1: Public / Open                                │
│    ├── Tier 2: Internal / Confidential                      │
│    ├── Tier 3: Restricted / Secret (PII, Financials, Keys)  │
│    └── Strict exfiltration & redaction rules                │
├─────────────────────────────────────────────────────────────┤
│ 3. Legal & Regulatory Compliance (法律与合规红线)           │
│    ├── Anti-trust, insider trading, and non-disparagement   │
│    ├── Mandatory legal disclaimers and copyright notices    │
│    └── Zero-tolerance violations requiring immediate freeze │
├─────────────────────────────────────────────────────────────┤
│ 4. Escalation & HITL Triggers (升级审批与人工复核机制)       │
│    ├── High-risk actions triggering mandatory confirmation  │
│    └── Designated compliance owner notification paths       │
└─────────────────────────────────────────────────────────────┘
```

---

## 4-Step Synthesis SOP (四阶治理规范提炼工作流)

```
Step 1: Ingestion & Document Scanning (制度文档摄取与结构解析)
   ├── Read raw compliance PDFs, Word handbooks, or security charters
   └── Identify explicit obligations, prohibitions, and discretionary guidance
Step 2: Tri-Pillar Classification (三维合规分类映射)
   ├── Map obligations into Brand Voice, Data Security, or Legal Redlines
   └── Discard rhetorical preamble and extract concrete behavioral rules
Step 3: Machine-Readable Rule Formulation (机器可执行约束编译)
   ├── Format rules into unambiguous deterministic preconditions
   └── Set strict violation actions (BLOCK, WARN, ESCALATE)
Step 4: Governance Pack Compilation (企业治理包沉淀导出)
   └── Output standard `governance/enterprise-policy.yaml` and human-readable brief
```

---

## Standard Output Contract (`enterprise-policy.yaml`)

```yaml
organization: "Acme Corporation"
version: "1.0.0"
effective_date: "2026-09-10"

brand_voice:
  tone: "Professional, Empathetic, Authoritative, Objective"
  prohibited_styles:
    - "Never use hyperbolic sales jargon (e.g. 'unbeatable', 'miraculous')"
    - "Never comment on speculative competitor rumors"
    - "Never issue binding financial forecasts without CFO sign-off"

data_classification:
  tier_1_public:
    handling: "Unrestricted external distribution"
  tier_2_internal:
    handling: "Workspace internal only; prevent public web search exposure"
  tier_3_restricted:
    patterns:
      - "Customer PII (SSN, ID numbers, credit cards)"
      - "Raw unencrypted API keys and database credentials"
      - "Unpublished quarterly financial earnings"
    action: "BLOCK_AND_REDACT"

legal_redlines:
  - id: "LEGAL_001"
    rule: "Mandatory GDPR / CCPA right-to-be-forgotten compliance"
    action: "ESCALATE_TO_DPO"
  - id: "LEGAL_002"
    rule: "All commercial proposals must include Standard Limitation of Liability clause"
    action: "BLOCK_UNTIL_CLAUSE_PRESENT"

escalation_matrix:
  security_incidents: "security-team@acme.corp"
  legal_inquiries: "legal-review@acme.corp"
```
