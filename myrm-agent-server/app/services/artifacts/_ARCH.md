# app/services/artifacts 模块架构

---

## 架构概述

工件只读公网分享：HMAC 令牌（含 `version_id` 版本锁定）+ 与 deploy 同规则的静态包（`share_bundle.py`，复用 `deploy.artifact_files.resolve_artifact_deploy_files(version_id=)`）。Bundle 重物化时精确使用 JWT 中锁定的版本。部署预检在 `app/services/deploy/preflight.py`。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `share_token.py` | 核心 | 创建/校验分享 token；`is_shareable_artifact`；token 可选 `typ` 字段 | ✅ |
| `share_bundle.py` | 核心 | `collect_deploy_files` 等价物落盘；public `/{token}/{path}` 安全读取；多文件 HTML 尾斜杠重定向 | ✅ |

---

## 依赖关系

- `app.api.files.artifact_share_api`（REST + public_router）
- `myrm_agent_harness.agent.artifacts.vault::ArtifactVault`（POS: 沙箱工件存储）
