---
name: mcp-reauth-watchdog
description: >-
  Proactive Model Context Protocol (MCP) authentication watchdog and credential expiry monitor.
  Sniffs OAuth tokens, API keys, and session leases before execution, trips warning and blocking gates,
  and orchestrates seamless token refreshes or interactive reauth workflows.
version: 1.0.0
category: operations
tags:
  - mcp
  - reauth-watchdog
  - credential-expiry
  - oauth-refresh
  - token-ttl
  - proactive-gate
  - MCP授权看门狗
  - 凭据续期
allowed-tools: file_write_tool file_read_tool bash_code_execute_tool
contract:
  steps:
    - 1. Credential TTL & Lease Probing (Probe expires_at timestamps and auth-check endpoints across configured MCP servers)
    - 2. Graded Expiry Gate Evaluation (Classify credential health into Safe >24h, Warning 1h-24h, or Blocking <=1h)
    - 3. Silent Refresh & Interactive Reauth Orchestration (Trigger silent OAuth refresh token grant or emit structured Reauth Card)
    - 4. Post-Refresh Health Verification (Execute secondary ping handshake to confirm credential renewal before resuming tasks)
  potential_traps:
    - description: Blindly continuing long-running multi-turn workflows when credentials expire within minutes
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Triggering full interactive reauth popups when silent background token refresh via refresh_token is possible
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Silently dropping failed reauth attempts leading to confusing HTTP 401 exceptions mid-task
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
    - description: Leaking refreshed secret tokens or API keys into markdown outputs or unencrypted terminal logs
      mitigation: Follow the skill SOP and verification_steps before proceeding; abort on ambiguity and surface the risk to the user
      severity: medium
  verification_steps:
    - Verify credential watchdog accurately detects near-expiry tokens (< 1 hour remaining)
    - Validate blocking gate halts agent execution before firing expired MCP tool requests
    - Confirm post-refresh probe asserts valid connection status before lifting execution gates
  success_criteria:
    - Zero mid-task OAuth expiration crashes, proactive warning cards, and automated zero-touch token renewals
---

# MCP Proactive Reauth & Expiry Watchdog (MCP 凭据主动重新认证与有效期看门狗)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

A dedicated skill for platform engineers, security leads, and autonomous agent workflows to actively monitor,
predict, and manage **Model Context Protocol (MCP)** credential expirations (OAuth2 access tokens, API key rotations, session leases).

It eliminates catastrophic mid-task crashes (e.g. an agent failing at turn 45 of a migration because a GitHub or Google Drive token expired)
by enforcing a **Proactive Authentication Health Gate** before executing any tool dependent on external authorization.

---

## The 4-Stage Proactive Reauth Pipeline (四阶主动重认证流水线)

```
Stage 1: Credential TTL & Lease Probing (凭据有效期主动探测)
   ├── Inspect `expires_at` metadata and query lightweight `/auth/status` endpoints
   └── Compute exact remaining Time-To-Live (TTL) for every active MCP server connection
Stage 2: Graded Expiry Gate Evaluation (三级分层临期门禁)
   ├── Safe Tier (TTL > 24 hours): Pass through seamlessly
   ├── Warning Tier (1 hour < TTL <= 24 hours): Log non-blocking notice and attempt background refresh
   └── Blocking Gate (TTL <= 1 hour or Expired): Halt tool invocation and trigger mandatory reauth
Stage 3: Silent Refresh & Interactive Reauth (静默续期与交互重认证)
   ├── Tier 1: Silent Refresh via OAuth `refresh_token` exchange (zero user interruption)
   └── Tier 2: Interactive Reauth Card via structured UI prompt if refresh token is absent or revoked
Stage 4: Post-Refresh Health Verification (刷新后二次确认)
   ├── Issue probe ping with newly acquired bearer token
   └── Resume paused agent task with 100% authorization confidence upon HTTP 200 response
```

---

## 1. Graded Expiry Gate Rules (分级临期门禁矩阵)

| Credential State | TTL Remaining | System Action | User Impact |
|---|---|---|---|
| **HEALTHY / SAFE** | > 24 Hours | Full bypass; standard execution | None |
| **EXPIRING SOON** | 1 Hour - 24 Hours | Asynchronous silent refresh trigger | Non-blocking toast/log: "Background token refresh initiated" |
| **CRITICAL / EXPIRED**| <= 1 Hour | **Hard Execution Block**: Tool invocation suspended | Emits structured **Reauth Card** with direct login action |
| **REVOKED / INVALID** | N/A (HTTP 401) | Immediate session isolation & quarantine | Emits critical auth alert; prompts re-binding |

---

## 2. Interactive Reauth Card Specification (`reauth_request`)

When silent refresh is impossible (e.g. initial login, SSO session expired, refresh token expired), emit this structured contract:

```markdown
### ⚠️ MCP 服务凭据临期/失效提醒

检测到外部工具服务 **[GitHub Enterprise MCP]** 的访问凭据即将失效（剩余有效期不足 30 分钟）。为防止任务执行中途崩溃，已触发前置安全阻断。

- **服务名称**: `github-enterprise-mcp`
- **所需权限范围 (Scopes)**: `repo`, `read:org`, `workflow`
- **当前状态**: `EXPIRED_SOON (TTL: 22m)`
- **续期动作**:
  - [点击一键进行 OAuth 重新授权](https://auth.internal.corp/mcp/github/reauth?session_id=myrm-7892)
  - 或在终端输入新生成的 Personal Access Token (PAT)
```

---

## 3. Deliverable Specification: Credential Audit Log (`docs/mcp-auth-audit.md`)

```markdown
# MCP Authorization Watchdog: Credential Health Status

## 1. Active MCP Server Credential Leases
| Server ID | Auth Type | Expiration Time | Remaining TTL | Watchdog Status | Action Taken |
|---|---|---|---|---|---|
| `github-tools` | OAuth2 Bearer | 2026-09-10 18:30:00 | 11h 25m | WARNING | Silent refresh scheduled |
| `jira-service` | API Token | 2026-12-31 23:59:59 | 112d | HEALTHY | None |
| `gdrive-storage`| OAuth2 Bearer | 2026-09-10 07:15:00 | 12m | BLOCKED | Reauth Card emitted |

## 2. Security Invariants
- Refreshed tokens must NEVER be logged to plaintext console output.
- All credential exchanges must occur through secure OS keychain or encrypted vault storage.
```
