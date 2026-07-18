# web-push/

Pure functions for Web Push click-through routing. `pushTargetUrl.ts` is the single implementation; `src/app/sw.ts` imports it and is bundled via `scripts/build-sw-src.mjs` before `serwist inject-manifest`.

| File | Role |
|------|------|
| `pushTargetUrl.ts` | Sanitize push payload URLs; resolve focus vs navigate when a window client is already open |
| `__tests__/pushTargetUrl.test.ts` | Unit tests for routing helpers |
| `__tests__/pushTargetUrl.swImport.test.ts` | Asserts `sw.ts` imports shared helpers and calls `client.navigate` on query mismatch |

Server-side event → URL mapping lives in `myrm-agent-server/app/core/web_push/push_deep_links.py`.

Chrome MCP E2E (seed via `POST /api/v1/approvals/test/seed-mock`):

| Test | Scenario |
|------|----------|
| `test_push_approval_deeplink_navigates_on_open_chat_tab` | Chat tab open → navigate `?approval=` → drawer + query strip |
| `test_push_approval_deeplink_cold_start_opens_drawer` | Cold load deeplink URL → drawer + query strip |
| `test_push_approval_deeplink_from_different_open_chat_tab` | Chat A open → navigate chat B deeplink → drawer on B |
| `test_push_approval_deeplink_unknown_id_strips_query_without_drawer` | Resolved pending + bogus `?approval=` → no drawer, query stripped |
