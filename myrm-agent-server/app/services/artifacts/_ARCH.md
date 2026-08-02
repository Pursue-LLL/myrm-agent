# services/artifacts 模块架构

---

## 架构概述

工件只读公网分享：HMAC 令牌（含 `version_id` 版本锁定）+ 与 publish 同规则的静态包（`share_bundle.py`，复用 `hosting.artifact_files.resolve_artifact_deploy_files(version_id=)`）。Bundle 重物化时精确使用令牌中锁定的版本。发布预检在 `app/services/hosting/preflight.py`。

支持可选密码保护：密码参与 HMAC key 派生（无状态设计，无需 DB 存储密码）。签名原语委托给 `app.core.security.share_hmac`。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `share_bundle.py` | 核心 | 物化 share 静态包 |
| `share_token.py` | 核心 | 工件分享令牌签发与校验（委托 share_hmac 通用签名层） |

---

## 依赖关系

- `app/core/security/share_hmac.py`（签名原语）
- `app/services/hosting/artifact_files.py`
- `app/services/hosting/preflight.py`
