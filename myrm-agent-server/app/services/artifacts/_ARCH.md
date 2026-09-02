# services/artifacts 模块架构

---

## 架构概述

工件只读公网分享：HMAC 令牌（含 `version_id` 版本锁定）+ 与 publish 同规则的静态包（`share/share_bundle.py`，复用 `hosting.artifact_files.resolve_artifact_deploy_files(version_id=)`）。Bundle 重物化时精确使用令牌中锁定的版本。发布预检在 `app/services/hosting/preflight.py`。

支持可选密码保护：密码参与 HMAC key 派生（无状态设计，无需 DB 存储密码）。签名原语委托给 `app.core.security.share.share_hmac`。

分享链接生命周期治理（`share/share_registry.py`）：创建时按 `sha256(token)` fingerprint 登记 DB（`ArtifactShareRecord`），GUI 可列出活跃链接并手动撤销。撤销为「物理删 bundle + 置 `revoked_at` 逻辑拒绝」双防线，并写审计日志：公开入口前置校验，撤销后 404 且拒绝重新 materialize（防复活）。清理分层：过期 bundle 磁盘文件按 TTL 清理，DB 记录保留 TTL + 60 天审计窗口后硬删（`ix_artifact_share_records_expiry` 复合索引加速 purge/活跃查询）。`GET /shares` 为纯读操作，无清理副作用（REST 语义）。

分享链接可复制展示（`share/share_token.py::rebuild_artifact_share_token`）：HMAC 令牌确定性生成，相同 payload + expiry 得到相同 token，因此无需落库存储原始 token，即可在列表接口中按需重建无密码分享链接（`share_path`）返回前端展示/复制；密码保护链接因密码不落库而无法重建，故 `register_share` 在登记时持久化 `share_path`（`ArtifactShareRecord.share_path` 列），列表接口优先返回持久化值，两类链接均可复制/打开。`artifact_share_api.py` 基于 `share_path` 组装绝对 `share_url`（前缀取 `app.core.infra.ingress::resolve_share_url_base` 共享公网 Ingress 分享 base，chat 与 artifact 双端复用），保证托管/隧道部署下链接外网可达；无 ingress 时 `share_url` 为 `null`，由前端按当前 origin 组装。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `share/`（子包） | 核心 | 工件分享子域：`share/share_bundle.py`（物化 share 静态包）、`share/share_token.py`（分享令牌签发/校验/重建）、`share/share_registry.py`（分享链接生命周期治理）。`share/__init__.py` 为聚合门面 |
| `bundle_builder.py` | 业务 | 提供 `build_zip_deliverable_bundle` 与 `generate_bundle_readme`，支持按 DeliverableManifest 分层流式压缩打包多工件资产 |

---

## 依赖关系

- `app.core.security.share.share_hmac.py`（签名原语）
- `app/services/hosting/artifact_files.py`
- `app/services/hosting/preflight.py`
- `app/database/models.artifact_share`（分享链接登记行）
- `app/database/models.artifact`（列表 join 取 artifact 名称）
