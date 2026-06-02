# services/config 模块架构


---

## 架构概述

用户配置业务逻辑层。提供配置 CRUD（含加密）、首次 onboarding 引导、健康监控、加密策略管理等业务服务。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `service.py` | 核心 | 配置 CRUD：set/get/get_all/sync/delete，含加密/解密管道和版本冲突检测 | ✅ |
| `encryption.py` | 核心 | 业务层加密策略：密钥注入、敏感配置判定、encrypt/decrypt 委托到 harness ConfigCrypto | ✅ |
| `migration.py` | 核心 | 配置加密迁移：明文→密文自动升级（启动时执行） | ✅ |
| `onboarding.py` | 核心 | 首次配置 onboarding：检查状态、标记完成、推荐 provider、probe 本地模型与搜索（SearXNG/DuckDuckGo） | ✅ |
| `health_monitor.py` | 核心 | 配置健康监控（周期性检查 provider 配置，proactive 通知用户） | ✅ |

---

## 核心功能

### 1. 配置 CRUD (`service.py`)

**职责**：配置存取、同步、版本控制（乐观锁）。

**核心函数**：
- `set_config()`：写入配置（自动加密敏感字段）
- `get_config()` / `get_all_configs()`：读取配置（自动解密）
- `sync_configs()`：批量同步（含版本冲突检测）
- `_encrypt_if_sensitive()`：写入前条件加密（含双重加密防护）
- `_decrypt_if_needed()`：读取后解密（含旧 key fallback 迁移 + 双重加密修复）

**解密 fallback 机制**：
1. 当前 key 解密 → 成功则返回
2. 如果失败，尝试 legacy device-fingerprint key → 成功则记录 WARNING 日志
3. 双重加密检测：解密后如果仍是 `{"_cipher": "..."}` 结构，自动再解密一层

### 2. 加密策略 (`encryption.py`)

**职责**：业务层加密决策（何时加密、用什么 key）。

**密钥来源**：
- **Sandbox 模式**：`settings.config_encryption_key`（控制平面提供）
- **Local 模式**：`resolve_local_encryption_key(state_dir)` → 优先 env var `CONFIG_ENCRYPTION_KEY` → 文件 `{state_dir}/.encryption_key` → 自动生成

**敏感配置范围**：
```
providers, retrieval, searchServices, mcpServers,
feishuCredentials, dingtalkCredentials, slackCredentials, ...
```

### 3. 配置迁移 (`migration.py`)

**职责**：自动迁移明文配置到加密格式。

**执行时机**：应用启动时（仅 Local 模式）。幂等操作。

### 4. Onboarding (`onboarding.py`)

**职责**：首次配置引导流程。

**核心函数**：
- `check_onboarding_status()`：检查用户是否已完成首次配置
- `complete_onboarding()`：标记首次配置完成
- `get_recommended_providers()`：返回推荐 provider 列表（Ollama/OpenAI/Anthropic）
- `probe_local_models()`：并发探测本地模型服务（Ollama:11434, LM Studio:1234），返回可用性、模型列表和延迟

### 5. 健康监控 (`health_monitor.py`)

**职责**：周期性检查 provider 配置健康，通过 SSE 推送通知。

---

## 依赖关系

### 内部依赖
- `app/database/models.py`：UserConfig 模型
- `app/platform_utils`：数据库 session 工厂等平台单例入口
- `app/api/config/schemas`：API 请求/响应模型

### 外部依赖
- `myrm_agent_harness.utils.crypto`：ConfigCrypto（AES-256-GCM 原语）、DecryptionError
- `myrm_agent_harness.utils`：resolve_local_encryption_key、get_device_fingerprint（legacy）

### 被依赖方
- `app/api/config/router.py`：API 层调用配置服务
- `app/main.py`：启动时执行迁移和健康监控
