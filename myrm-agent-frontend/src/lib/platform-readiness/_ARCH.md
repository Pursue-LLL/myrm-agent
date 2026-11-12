# platform-readiness

## 职责

本地开发/WebUI 模式下，在 backend SQLite 就绪前阻止 ConfigSync、approvals recovery、TauriAdapter 等业务 API。

## 状态机

`warming → ready | unreachable`

- 探测顺序：`waitForBackendReady()` → `GET /api/v1/health/ready`（`checks.database`）
- 预算：`/health` 阶段按部署模式取 `getBackendHealthMaxAttempts()`（桌面壳 135 s，其余 60 s；桌面壳的 sidecar 归壳管，壳先放弃之前这里不报 `unreachable`）；`/health/ready` 阶段固定 60 s
- 失效：`markLocalBackendUnreachable()`（运输层 facade，联动 `markPlatformUnreachable()`）

## 订阅方

- `lib/backend-health.ts` — `ensureLocalBackendReady()` 委托 `whenDatabaseReady()`；`markLocalBackendUnreachable()` 为运输失败统一入口
- `settings-sync-initializer.tsx`
- `usePendingApprovalsRecovery.ts`
- `services/config/adapters/TauriAdapter.ts` — 5xx/transport 调 `markLocalBackendUnreachable()`
