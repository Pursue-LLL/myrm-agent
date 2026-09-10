---
name: github-skill-dynamic-installer
description: >-
  Zero-config dynamic installer and sandbox auditor for external Agent Skills distributed via
  GitHub repositories. Clones target repos in ephemeral isolation, conducts multi-layer security
  audits (AST, command safety, prompt injection, and credential leak risks), verifies frontmatter
  and contract integrity, and performs non-restart hot-mounting into the active runtime.
version: 1.0.0
category: engineering
tags:
  - github-installer
  - skill-installer
  - sandbox-audit
  - dynamic-mount
  - security-sandbox
  - zero-config
allowed-tools: file_read_tool file_write_tool bash_code_execute_tool memory_search_tool
contract:
  steps:
    - "Phase 1: URL Validation & Ephemeral Ingestion — parse GitHub URL/commit ref, shallow clone into ephemeral sandbox directory"
    - "Phase 2: Multi-Layer Security & Static Audit — scan for reverse shells, prompt injection vectors, hardcoded secrets, and destructive scripts"
    - "Phase 3: Frontmatter Schema & Contract Validation — verify SKILL.md specification, allowed-tools declaration, and execution boundaries"
    - "Phase 4: Dynamic Hot-Mounting & Registry Activation — copy to validated skills storage and register in runtime catalog without server reboot"
  potential_traps:
    - description: "Blindly executing setup.py, install scripts, or untrusted build artifacts from the cloned repository"
      mitigation: "Strict read-only inspection: execute all checks via AST parsers and regex scanners without invoking external install scripts"
      severity: high
    - description: "Installing a skill that collides with or overrides a core system-protected skill"
      mitigation: "Check candidate skill ID against immutable core blacklist before proceeding with registry insertion"
      severity: high
    - description: "Prompt injection payloads concealed within sample prompts or documentation"
      mitigation: "Run specialized prompt safety scanner on all markdown sections before activating"
      severity: medium
  verification_steps:
    - step_id: security_audit_passed
      description: "Verifies zero high-severity vulnerabilities (no destructive commands, no credential exfiltration patterns)"
      validation_method: "Inspect audit log for clean security attestation"
      is_required: true
    - step_id: hot_mount_verified
      description: "Verifies newly installed skill is discoverable in the skills catalog"
      validation_method: "Verify skill manifest exists in target skills directory"
      is_required: true
  success_criteria: "Securely ingests, audits, and activates an external GitHub-hosted skill in an ephemeral sandbox without system downtime or security degradation."
  estimated_duration_seconds: 120
---

# GitHub URL Zero-Config Dynamic Skill Installer & Sandbox Auditor

## Overview

External developer ecosystems frequently publish innovative skills as open-source GitHub repositories.
Manually downloading, reviewing, placing, and restarting services creates substantial friction and
introduces severe security hazards (e.g. prompt injection, unauthorized network exfiltration, or
arbitrary command execution).

The `github-skill-dynamic-installer` skill provides an automated, zero-config onboarding workflow:
it clones candidate repositories in an isolated ephemeral sandbox, executes comprehensive static and
security audits, verifies contract compatibility, and performs safe, non-restart hot-mounting.

---

## 4-Phase Installation & Audit SOP

### Phase 1: URL Validation & Ephemeral Ingestion
1. **URL Normalization**: Validate GitHub URL structure (`https://github.com/{owner}/{repo}` or branch/subfolder links).
2. **Ephemeral Shallow Clone**: Clone only depth=1 into a dedicated scratch directory (`/tmp/ephemeral_skills/{nonce}/`).
3. **Artifact Discovery**: Locate root or subfolder `SKILL.md` candidates.

### Phase 2: Multi-Layer Security & Static Audit (4 Mandatory Gates)

| Security Gate | Detection Strategy | High-Risk Indicator (Auto-Reject) |
|---|---|---|
| **1. Command Safety** | AST / Regex parsing of all bash scripts and python snippets | `rm -rf`, `curl \| sh`, reverse shells, `dd`, fork bombs |
| **2. Secret Leak Prevention** | Entropy scan + API key pattern match | Hardcoded bearer tokens, AWS credentials, private keys |
| **3. Prompt Injection Defense** | Pattern detection for jailbreak directives | "Ignore previous instructions", system prompt exfiltration |
| **4. ID Collision Gate** | Blacklist comparison | Overriding protected system skills (`bash_code_execute`, `core-*`) |

### Phase 3: Frontmatter Schema & Contract Validation
- Confirm valid YAML frontmatter delimiters (`---`).
- Verify required fields: `name`, `description`, `version`, `allowed-tools`.
- Inspect `contract.steps` and `verification_steps` for completeness.

### Phase 4: Dynamic Hot-Mounting & Registry Activation
- Move audited skill bundle to active skills storage directory (`skills/{skill_name}/`).
- Trigger runtime metadata cache refresh so the skill is immediately discoverable in chat and settings.
- Output installation receipt with version, capabilities, and audit checksum.

---

## Output Contract & Audit Receipt

Upon successful installation, the skill outputs a structured receipt:
- **Skill Name & Version**: e.g., `community-latex-renderer v1.2.0`
- **Security Attestation**: 4/4 Audit Gates Passed (Zero critical findings)
- **Mount Path**: `skills/community-latex-renderer/SKILL.md`
- **Activation Status**: Active (Available for immediate turn binding)
