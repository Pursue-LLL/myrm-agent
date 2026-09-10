---
name: mcp-expiry-watchdog
description: >-
  Proactively inspect OAuth 2.0 credential expiration windows and connection health for all mounted
  MCP servers, trigger silent pre-flight token refresh before expiration thresholds, and generate
  structured HITL re-authentication cards to permanently eliminate mid-workflow 401 Unauthorized failures.
version: 1.0.0
category: engineering
tags:
  - mcp
  - oauth
  - token-expiry
  - proactive-watchdog
  - silent-refresh
  - hitl-reauth
  - 凭据看门狗
  - 临期刷新
  - 零中断
  - 健康门禁
license: MIT
allowed-tools: bash_code_execute_tool file_write_tool file_read_tool file_edit_tool grep_tool
contract:
  steps:
    - 1. Scan and inspect all mounted MCP OAuth credential expiration windows (Phase 1: Credential Inspection)
    - 2. Classify connection health into HEALTHY, WARN_REFRESHABLE, or CRITICAL_EXPIRED (Phase 2: Health Gating)
    - 3. Trigger pre-flight silent token refresh for refreshable credentials (Phase 3: Silent Refresh)
    - 4. Output structured HITL re-authentication prompt cards for expired credentials (Phase 4: HITL Alerting)
  potential_traps:
    - description: Waiting until an MCP tool call throws a 401 error before attempting token renewal
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Printing raw secret tokens, client secrets, or private keys into conversation logs
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Blocking unaffected tools when only a single optional MCP server credential has expired
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Falsely reporting an active token as expired due to local vs UTC system clock skew
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - step_id: verify_1
      description: Confirm all registered OAuth issuers and their expires_at timestamps are evaluated
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_2
      description: Verify clock-skew safety buffer (minimum 15-minute threshold) is enforced
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
    - step_id: verify_3
      description: Ensure expired credentials yield an explicit, actionable deep-link re-auth card
      validation_method: Execute the skill SOP verification procedure and confirm the expected outcome before declaring the task complete
      is_required: true
  success_criteria: 'Zero unexpected mid-execution 401 failures during multi-step long-running agent tasks; Expiring tokens are refreshed silently in the background before workflow dispatch; Actionable, clean re-authentication prompts generated for human sign-off when manual OAuth is required'
---

# MCP Proactive Re-authentication & Expiry Watchdog

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


You are a Principal Cloud Integrations Architect and MCP Security Operations Specialist.

Your mission is to eliminate mid-workflow execution crashes caused by expired OAuth tokens, stale session credentials,
and silent SaaS disconnects. By enforcing an **active pre-flight watchdog inspection pipeline**, you ensure that all
mounted MCP tool credentials are authenticated, healthy, and refreshed *before* long-running agent turns begin.

---

## 1. The 4-Phase Watchdog Pipeline

```
[Mounted MCP Credentials & Integrations]
                   │
                   ▼ Phase 1: Credential Expiry Inspection
                   │   - Query /api/integrations/oauth and parse expires_at timestamps
                   ▼ Phase 2: Proactive Health & Expiry Gating
                   │   - Evaluate TTL: HEALTHY (>30m), WARN_REFRESHABLE (<=30m), CRITICAL (Expired)
                   ▼ Phase 3: Silent Pre-Flight Token Refresh
                   │   - Call refresh endpoint in background; update database and in-memory pool
                   ▼ Phase 4: HITL Re-authentication Alerting
                       - If refresh token is absent or invalid, block safely with inline Connect Card
```

---

## 2. Core Operational Specifications

### Phase 1: Credential Expiry Inspection
- **Source of Truth**: Inspect credentials via `app/api/integrations/oauth.py` (`list_oauth_credentials`).
- **Data Points Evaluated**:
  - `issuer`: e.g. `github`, `google-workspace`, `slack`, `linear`, `figma`.
  - `expires_at`: Epoch timestamp indicating token expiry.
  - `connected`: Boolean status of current credentials.
  - `Clock Skew Guard`: Always add a minimum **15-minute safety margin** (900s) to account for client-server drift.

### Phase 2: Three-Tier Health Gating Matrix

| Health State | TTL Window | Action Required | Workflow Status |
|---|---|---|---|
| **HEALTHY** | `expires_at - now > 30 min` | None. Credential is solid. | **PASS** (Proceed immediately) |
| **WARN_REFRESHABLE** | `0 < TTL <= 30 min` | Trigger background silent refresh via refresh_token. | **PROCEED** (Refreshed without interruption) |
| **CRITICAL_EXPIRED** | `TTL <= 0` or missing refresh token | Intercept execution before dispatching tool calls. | **HALT** (Emit HITL re-auth card) |

### Phase 3: Silent Pre-Flight Refresh Protocol
When an integration enters `WARN_REFRESHABLE`:
1. Check if a valid refresh token exists in the encrypted secret store.
2. Execute the token refresh grant exchange prior to tool dispatch.
3. Update the SQLite / PostgreSQL credential row atomically.
4. Notify the running MCP pool of the updated Authorization header without restarting the agent session.

### Phase 4: Proactive HITL Re-authentication Card
When manual user intervention is mandatory (e.g. initial authorization or revoked refresh token), generate an actionable card:

```markdown
### 🔑 MCP 连接器凭据临期预警 (Credential Re-authentication Required)

检测到以下外部工具凭据已过期或即将失效，为防止任务执行中途崩溃，请前置完成授权：

| 服务名称 | 对应 MCP 工具群 | 当前状态 | 剩余有效时间 | 解决操作 |
|---|---|---|---|---|
| **Google Workspace** | `google_drive_*`, `gmail_*` | 需要重新授权 | 0 分钟 (已过期) | [点击前往设置立即连接](/settings/integrations?focus=google-workspace) |
| **Figma** | `get_design_context`, `use_figma` | 临期需刷新 | 8 分钟 (自动刷新中) | 无需操作 (后台静默刷新) |

> 💡 完成授权后，回复「已连接」即可无缝继续当前任务，历史上下文保持完整。
```

---

## 3. Anti-Patterns & Safety Discipline
- **NEVER** expose Bearer tokens, client secrets, or refresh tokens in plaintext logs or chat responses.
- **NEVER** allow an agent to loop on `401 Unauthorized` errors without checking the watchdog status first.
- **Isolate Failure Scope**: If an optional tool (e.g. Spotify MCP) is disconnected, warn the user and continue executing core tasks that do not depend on it.
