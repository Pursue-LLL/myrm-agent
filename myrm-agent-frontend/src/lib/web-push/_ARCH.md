# web-push/

## 架构概述

Pure functions for Web Push **click-through routing** in the Service Worker. No React, no fetch — shared SSOT for `src/app/sw.ts` (esbuild bundle via `scripts/build-sw-src.mjs`).

HTTP subscription client: `services/web-push.ts`. React lifecycle: `hooks/usePushSubscription.ts`.

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `pushTargetUrl.ts` | 核心 | Sanitize push payload URLs; resolve focus vs navigate on open clients | ✅ |
| `__tests__/pushTargetUrl.test.ts` | 测试 | Unit tests for routing helpers | — |
| `__tests__/pushTargetUrl.swImport.test.ts` | 测试 | Asserts `sw.ts` imports shared helpers + `client.navigate` | — |

## 模块依赖

- **被依赖**：`src/app/sw.ts` (bundled into `public/sw.js`)
- **对齐 server SSOT**：`myrm-agent-server/app/core/web_push/push_deep_links.py`
- **路由段同步**：`RESERVED_APP_SEGMENTS` ↔ `src/app/_ARCH.md` 路由表

## Chrome MCP E2E

Seed: `POST /api/v1/approvals/test/seed-mock` · File: `myrm-agent-server/tests/e2e/test_push_approval_deeplink_chrome_e2e.py`

| Test | Scenario |
|------|----------|
| `test_push_approval_deeplink_navigates_on_open_chat_tab` | Chat tab open → navigate `?approval=` → drawer + query strip |
| `test_push_approval_deeplink_cold_start_opens_drawer` | Cold load deeplink URL → drawer + query strip |
| `test_push_approval_deeplink_from_different_open_chat_tab` | Chat A open → navigate chat B deeplink → drawer on B |
| `test_push_approval_deeplink_unknown_id_strips_query_without_drawer` | Resolved pending + bogus `?approval=` → no drawer, query stripped |
