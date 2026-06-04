# app/services/artifacts 模块架构

---

## 架构概述

工件只读公网分享：无状态 HMAC 令牌与 vault 内容解析。部署预检逻辑在 `app/services/deploy/preflight.py`。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `share_token.py` | 核心 | 创建/校验分享 token；可分享文件名后缀白名单 | ✅ |
| `share_resolve.py` | 核心 | 按 artifact+version 解析 vault 路径与 MIME | ✅ |

---

## 依赖关系

- `app.api.files.artifact_share_api`（REST + public_router）
- `myrm_agent_harness.agent.artifacts.vault::ArtifactVault`（POS: 沙箱工件存储）
