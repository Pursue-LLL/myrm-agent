# security 模块架构


---

## 架构概述

业务层安全模块，专注于单租户业务配置加密和安全存储。设计理念：简单优于复杂，专注核心威胁，避免过度设计。

**职责分层**：
- **框架层** (`myrm-agent-harness`): 通用权限策略引擎、6层安全防御、SSRF防护、凭证加密存储
- **业务层** (本模块): MasterKey 派生、业务配置加密策略、浏览器Session加密

在 Agent-in-Sandbox 架构下，Server 层是单用户服务：
- 渠道 Webhook 的签名校验由各渠道适配器（`app/channels/providers/`）自行完成

---

## 目录结构

```
security/
├── __init__.py          # 模块入口，导出 MasterKeyProvider
├── _ARCH.md             # 本文档
├── master_key.py        # MasterKeyProvider（零落盘密钥管理）
├── config_crypto.py     # 敏感配置key检测（字段级）
├── browser_vault.py     # SessionVault 实例管理（全局 + agent 级隔离）与全保险库过期清理
├── llm_reviewer.py      # 动态 LLM 适配器（Transcript Classifier）
├── pii_actions.py       # PII action 字符串安全解析（非法/缺失值回退默认，防崩溃）
├── privacy_settings.py  # 持久化隐私设置 → 无 web 请求入口（渠道/定时/语音/目标/看板/唤醒）的 agent 隐私参数，与进程级隐私策略的构造
├── privacy_policy_sync.py  # 把已保存的隐私设置发布为 harness 进程级策略（启动时 + 每次个人设置保存后）
├── integration_write_patterns.py # 业务层 shell 命令分析集成写模式（委托框架层注册）
├── auth/                # 认证原语子包（identity、public paths、session helpers）
└── share/               # 分享链接安全子包（HMAC 签名、隐私头、失效页、解锁 cookie、密码门）
```

**注意**：
- 权限策略引擎在框架层 `myrm_agent_harness.agent.security`
- 渠道 Webhook 签名校验在各渠道适配器 `app/channels/providers/`
- 凭证加密存储在框架层 `app.channels.storage`
- 配置加密服务在 `app/services/config/encryption.py`（业务层策略注入）

---

## 文件清单

| 文件 | 职责 |
|------|------|
| `master_key.py` | MasterKeyProvider，3 级获取 Master Key：环境变量 (SaaS) → OS Keyring (Local/Tauri) → VaultLockedError (需用户解锁)。零落盘 (Zero-Disk) 架构，绝不向硬盘写明文密钥。 |
| `config_crypto.py` | 敏感配置字段检测（关键词匹配 + 精确 key 匹配，如 browserCloudProvider、egress_proxy、llm_proxy 等） |
| `browser_vault.py` | SessionVault 实例管理：全局单例（非 agent 场景）+ 按 agent_id 物理隔离的 agent vault；`cleanup_all_vaults` 一次清理全局 + 全部 agent vault 的过期会话（API 与 DB 维护定时任务共用） |
| `llm_reviewer.py` | 动态 Transcript Classifier 适配器，运行时获取用户 LLM 实例 |
| `pii_actions.py` | 持久化 PII action 字符串安全解析：缺失/非法值回退默认枚举，杜绝非法配置导致 agent 初始化或记忆提取崩溃（retry 与 security extension 共用） |
| `privacy_settings.py` | 读取持久化个人设置里的隐私设置（privacyEnabled / S2 / S3 / deep scan / 自定义关键词·正则·敏感工具）：`privacy_agent_params` 供所有服务端自建的 `GeneralAgentParams`（渠道、定时、语音×2、目标、看板、唤醒）；`resolve_privacy_params` 供 web 对话——请求写明的优先，请求没说的跟随已保存设置；`privacy_policy_from_params` 把一组完整的隐私字段构造成 `PrivacyPolicy`（`privacy_policy_from_settings` 用它构造进程级策略，设置页「试一试」预览用它构造草稿策略）。本地路由（privacy_routing）仍仅随请求 |
| `privacy_policy_sync.py` | `sync_privacy_policy` / `apply_privacy_policy_from_db`：把已保存的设置发布给 harness（`set_process_privacy_policy`），使标题/建议/离线压缩/会议纪要等不经过 agent 主循环的模型调用由 harness 出站闸门统一脱敏。启动时调用一次，`ConfigService` 每次写入 `personalSettings` 后再调用，无需逐调用点脱敏 |
| `auth/`（子包） | 认证原语子包，含 `control_plane_guard.py`（CP 鉴权、内部端点 Origin/Host 门禁、Fail-Closed 本地回环检查）等 |
| `share/`（子包） | 分享链接安全子域，含 5 个模块：`share_hmac.py`（HMAC-SHA256 签名层 + token_fingerprint）、`share_headers.py`（隐私头常量）、`share_status_page.py`（失效页/JSON 404 分流）、`share_unlock.py`（解锁 cookie 机制）、`share_password_page.py`（密码门页面）。`share/__init__.py` 为聚合门面，统一 re-export。 |
| `integration_write_patterns.py` | 业务层 shell 命令分析的集成写模式：委托框架层 `register_integration_write_patterns` 注册 |

---

## 安全原语分布

| 安全原语 | 所在层 | 具体位置 |
|----------|--------|----------|
| AES-256-GCM 配置加密 | 框架层 | `myrm_agent_harness.utils.crypto.config_crypto` |
| Fernet 凭证加密 | 框架层 | `app.channels.storage.credentials_store` |
| SSRF 防护 | 框架层 | `myrm_agent_harness.toolkits.mcp.security` |
| 权限策略引擎 | 框架层 | `myrm_agent_harness.agent.security` |
| MasterKey 管理 | 业务层 | `app/core/security/master_key.py` |
| 加密策略决策 | 业务层 | `app/services/config/encryption.py` |
| 分享链接 HMAC + 密码门 | 业务层 | `app/core/security/share_hmac.py` |
| 分享解锁 cookie 机制 | 业务层 | `app/core/security/share_unlock.py` |
| 内部服务认证 | 业务层 | `app/api/dependencies.py` |

---

## 依赖关系

### 外部依赖
- `keyring`: OS 原生密钥链（macOS Keychain / Linux secret-service / Windows Credential Manager）
- `myrm_agent_harness.utils.crypto`: 框架层 AES-256-GCM 加密工具
- `myrm_agent_harness.agent.security`: 框架层权限策略引擎

### 被依赖
- `app/services/config/encryption.py`: 配置存储透明加解密
- `app/core/channel_bridge/config_loader.py`: 频道配置加载解密
- `app/core/cron/crypto.py`: 定时任务配置加密（委托）
- `app/api/dependencies.py`: 内部服务密钥验证
