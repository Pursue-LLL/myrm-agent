# security 模块架构


---

## 架构概述

业务层安全模块，专注于单租户业务配置加密和安全存储。设计理念：简单优于复杂，专注核心威胁，避免过度设计。

**职责分层**：
- **框架层** (`myrm-agent-harness`): 通用权限策略引擎、6层安全防御、SSRF防护、Nonce防重放、HMAC签名验证、凭证加密存储
- **业务层** (本模块): MasterKey 派生、业务配置加密策略、浏览器Session加密

在 Agent-in-Sandbox 架构下，Server 层是单用户服务：
- Nonce 管理和 HMAC 签名验证由框架层 `myrm_agent_harness.infra.security` 提供
- SecurityMiddleware 实现在 `app/middleware/security.py`；**默认不在 `middlewares.py` register**（SaaS 由 CP 反代隔离）

---

## 目录结构

```
security/
├── __init__.py          # 模块入口，导出 MasterKeyProvider
├── _ARCH.md             # 本文档
├── master_key.py        # MasterKeyProvider（零落盘密钥管理）
├── config_crypto.py     # 敏感配置key检测（字段级）
├── browser_vault.py     # 浏览器 SessionVault 全局单例
└── llm_reviewer.py      # 动态 LLM 适配器（Transcript Classifier）
```

**注意**：
- 权限策略引擎在框架层 `myrm_agent_harness.agent.security`
- Nonce/Signature/Timestamp 验证在框架层 `myrm_agent_harness.infra.security`
- 凭证加密存储在框架层 `app.channels.storage`
- SecurityMiddleware 在 `app/middleware/security.py`（默认未挂载；可选 WebUI Remote 直连场景启用）
- 配置加密服务在 `app/services/config/encryption.py`（业务层策略注入）

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `master_key.py` | MasterKeyProvider，3 级获取 Master Key：环境变量 (SaaS) → OS Keyring (Local/Tauri) → VaultLockedError (需用户解锁)。零落盘 (Zero-Disk) 架构，绝不向硬盘写明文密钥。 |
| `config_crypto.py` | 敏感配置字段检测（api_key/secret/password/token 等关键词匹配） |
| `browser_vault.py` | 全局 SessionVault 单例管理（浏览器会话加密持久化） |
| `llm_reviewer.py` | 动态 Transcript Classifier 适配器，运行时获取用户 LLM 实例 |

---

## 安全原语分布

| 安全原语 | 所在层 | 具体位置 |
|----------|--------|----------|
| AES-256-GCM 配置加密 | 框架层 | `myrm_agent_harness.utils.crypto.config_crypto` |
| Fernet 凭证加密 | 框架层 | `app.channels.storage.credentials_store` |
| Nonce 防重放 | 框架层 | `myrm_agent_harness.infra.security.nonce` |
| HMAC-SHA256 签名 | 框架层 | `myrm_agent_harness.infra.security.signature` |
| Timestamp 窗口验证 | 框架层 | `myrm_agent_harness.infra.security.signature` |
| SSRF 防护 | 框架层 | `myrm_agent_harness.toolkits.mcp.security` |
| 权限策略引擎 | 框架层 | `myrm_agent_harness.agent.security` |
| MasterKey 管理 | 业务层 | `app/core/security/master_key.py` |
| 加密策略决策 | 业务层 | `app/services/config/encryption.py` |
| 安全中间件集成 | 业务层 | `app/middleware/security.py` |
| 内部服务认证 | 业务层 | `app/api/dependencies.py` |

---

## 依赖关系

### 外部依赖
- `keyring`: OS 原生密钥链（macOS Keychain / Linux secret-service / Windows Credential Manager）
- `myrm_agent_harness.infra.security`: 框架层 Nonce/Signature/Timestamp
- `myrm_agent_harness.utils.crypto`: 框架层 AES-256-GCM 加密工具
- `myrm_agent_harness.agent.security`: 框架层权限策略引擎

### 被依赖
- `app/middleware/security.py`: SecurityMiddleware（sandbox模式启用）
- `app/services/config/encryption.py`: 配置存储透明加解密
- `app/core/channel_bridge/config_loader.py`: 频道配置加载解密
- `app/core/cron/crypto.py`: 定时任务配置加密（委托）
- `app/api/dependencies.py`: 内部服务密钥验证
