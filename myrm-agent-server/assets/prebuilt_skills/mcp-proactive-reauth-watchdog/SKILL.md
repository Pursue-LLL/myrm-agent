---
name: mcp-proactive-reauth-watchdog
description: "Proactive OAuth credential introspection, expiration watchdog probe, silent token refresh, and graceful user reauthorization gate for uninterrupted MCP toolchains."
version: "1.0.0"
category: "architecture"
tags:
  - mcp
  - oauth
  - token-refresh
  - credential-watchdog
  - proactive-reauth
  - hermes-agent
allowed-tools:
  - bash_code_execute_tool
  - file_read_tool
  - file_write_tool
---

# MCP Proactive Reauth & Credential Expiration Watchdog Protocol (MCP 凭据主动探活与临期轮转看门狗协议)

## Bash execution contract

When calling `bash_code_execute_tool`, always pass **`reason`** (≥10 characters: why this command runs) and **`command`**. Put `reason` first.


## Overview

Based on architecture principles from Hermes Agent v0.21.0 Pantheon ("Pantheon Release: MCP Command Center & Proactive Reauth"), this skill eliminates **mid-execution credential failures** (the "Passive 401 Unauthorized Trap").
Rather than waiting for an MCP tool call to fail mid-turn with expired OAuth tokens, this watchdog actively audits credential TTLs, performs automated silent refreshes before expiration thresholds, and triggers structured user re-authorization gates before tasks start.

---

## 1. Credential Health Status Matrix (凭据健康度四级状态机)

| 状态等级 | TTL 剩余有效时间 | 动作策略 | 对下游任务的影响 |
|---|---|---|---|
| **HEALTHY** | TTL > 30 分钟 | 放行调用，无需干预 | 零延迟无感执行 |
| **EXPIRING_SOON** | 5 分钟 < TTL <= 30 分钟 | 触发后台异步静默刷新 (Silent Refresh) | 零延迟无感执行 |
| **REFRESH_REQUIRED** | TTL <= 5 分钟 (或已过期) | 阻塞当前调用，同步执行 OAuth 刷新换取新 Access Token | 增加 <500ms 刷新握手耗时 |
| **HUMAN_REAUTH_REQUIRED** | Refresh Token 失效或被注销 | 拦截任务，抛出交互式重新授权向导卡片 | 等待用户在 UI 点击重连 |

---

## 2. The 4-Phase Watchdog Lifecycle

```
[Task Initiated / Background Cron] ──> [1. Credential Introspection & TTL Probe]
                                                       │
                                                       ▼
                                       [2. Health Classification & Gate Routing]
                                                       │
                                                       ▼
                                       [3. Automated Silent Token Rotation]
                                                       │
                                                       ▼
                                       [4. Dashboard Sync & Human Gate Closure]
```

### Phase 1: Credential Introspection & TTL Probe (凭据元数据嗅探)
- Read stored MCP credentials (e.g. `~/.myrm/credentials/mcp_tokens.json`).
- Calculate remaining time: `ttl = expires_at - current_timestamp()`.
- For stateless servers or opaque tokens, send a lightweight probe (`tools/list` or ping).

### Phase 2: Health Classification & Gate Routing (健康度分流)
- Match against the 4-level status matrix.
- If `HEALTHY`, pass through immediately.
- If `EXPIRING_SOON` or `REFRESH_REQUIRED`, branch to Phase 3.
- If refresh grant is denied/expired, branch to Phase 4.

### Phase 3: Automated Silent Token Rotation (自动化静默轮转)
- Make a standard OAuth 2.0 POST request:
  ```bash
  POST {token_endpoint}
  grant_type=refresh_token&refresh_token={stored_refresh_token}&client_id={id}
  ```
- Atomically persist the new `access_token` and updated `expires_at` timestamp.
- Never write credentials into conversation logs or git tracking.

### Phase 4: Dashboard Sync & Human Gate Closure (仪表盘同步与人机卡片)
- Update local MCP Command Center health status.
- If human intervention is mandatory, output a Reauthorization Card:
  - **Connector**: `Google Drive MCP` / `Slack MCP`
  - **Status**: `Needs Reauth`
  - **Reason**: `Refresh token expired on 2026-09-09`
  - **Action Link**: Direct user to `/settings/integrations?reauth=google`

---

## 3. Pre-flight Verification Gate

Before invoking any authenticated MCP tool:
- [ ] Credential status is confirmed `HEALTHY` or successfully rotated.
- [ ] No plaintext secrets or client secrets are exposed in logs.
- [ ] In-memory and persistent credential stores are strictly synchronized.
