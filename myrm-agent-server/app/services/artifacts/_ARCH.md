# services/artifacts 模块架构

---

## 架构概述

工件只读公网分享：HMAC 令牌（含 `version_id` 版本锁定）+ 与 publish 同规则的静态包（`share_bundle.py`，复用 `hosting.artifact_files.resolve_artifact_deploy_files(version_id=)`）。Bundle 重物化时精确使用令牌中锁定的版本。发布预检在 `app/services/hosting/preflight.py`。

支持可选密码保护：密码参与 HMAC key 派生（无状态设计，无需 DB 存储密码）。签名原语委托给 `app.core.security.share_hmac`。

分享链接生命周期治理（`share_registry.py`）：创建时按 `sha256(token)` fingerprint 登记 DB（`ArtifactShareRecord`），GUI 可列出活跃链接并手动撤销。撤销为「物理删 bundle + 置 `revoked_at` 逻辑拒绝」双防线：公开入口前置校验，撤销后 404 且拒绝重新 materialize（防复活）。清理分层：过期 bundle 磁盘文件按 TTL 清理，DB 记录保留 TTL + 60 天审计窗口后硬删（`ix_artifact_share_records_expiry` 复合索引加速 purge/活跃查询）。`GET /shares` 为纯读操作，无清理副作用（REST 语义）。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `share_bundle.py` | 核心 | 物化 share 静态包 |
| `share_token.py` | 核心 | 工件分享令牌签发与校验（委托 share_hmac 通用签名层） |
| `share_registry.py` | 核心 | 分享链接生命周期登记/列表/撤销/TTL 清理（`ArtifactShareRecord`） |

---

## 依赖关系

- `app/core/security/share_hmac.py`（签名原语）
- `app/services/hosting/artifact_files.py`
- `app/services/hosting/preflight.py`
- `app/database/models.artifact_share`（分享链接登记行）
- `app/database/models.artifact`（列表 join 取 artifact 名称）
