# platform_utils/sandbox 模块架构


---

## 子模块

| 模块 | 职责 |
|------|------|
| `entitlements/` | Control Plane 配额客户端（cron/ingress/subagent/VNC entitlements + WU budget adapter） |
| `storage.py` | S3StorageBackend（需 aioboto3；缺包报错提示 `uv sync`） |

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `entitlements/entitlement_guard.py` | ✅ 核心 | CP `/api/internal/billing/entitlements` 客户端 | ✅ |
| `entitlements/platform_budget_adapter.py` | ✅ 核心 | CP Work Unit reserve/commit/release | ✅ |
| `storage.py` | 辅助 | S3 云对象存储后端 | ⚠️ |
