# External Agent Skill Bridge Service Architecture

## Overview
The `skill_bridge` service orchestrates bi-directional memory synchronization and skill installation between the Myrm Server and third-party developer agent environments (Cursor, Claude Code, Codex, Hermes, OpenClaw).

## Architecture & Principles
1. **Isolated Instruction Blocks**:
   Utilizes Harness `ExternalAgentSkillWriter` and `SafeMarkerInjector` to manipulate target rules files (.cursorrules, CLAUDE.md, etc.) safely without disturbing preexisting user rules.
2. **Sub-20ms Memory Gateway**:
   Exposes high-speed, low-latency REST recall endpoint (`/api/memory/external/query`) designed for tool invocations from external command-line agents.
3. **Secret Redaction & Contribution Guard**:
   Provides an ingestion endpoint (`/api/memory/external/contribute`) that filters high-entropy secrets using `ShannonEntropyInspector` and scrubs known credentials using `LocalSecretRedactor` before committing to persistent storage.
4. **Third-Party Conflict Mitigation**:
   Scans existing configuration files for conflicting legacy memory plugins (Mem0, Zep, SQLite memory) to alert users and prevent race conditions.

## Modules
- `service.py`: Singleton `ExternalAgentSkillBridgeService` coordinating target scanning, installation, querying, and sanitization.
