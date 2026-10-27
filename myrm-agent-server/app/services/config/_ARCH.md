# services/config 模块架构


---

## 架构概述

用户配置业务逻辑层。提供配置 CRUD（含加密）、首次 onboarding 引导、健康监控、加密策略管理等业务服务。

---

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `service.py` | 核心 | 配置 CRUD：set/get/get_all/sync/delete，含加密/解密管道和版本冲突检测；`create_initial_version` / `increment_version` 是版本号的唯一生成处，启动迁移同用 | ✅ |
| `encryption.py` | 核心 | 业务层加密策略：密钥注入、敏感配置判定、encrypt/decrypt 委托到 harness ConfigCrypto | ✅ |
| `migration.py` | 核心 | 配置加密迁移：明文→密文自动升级；`seal_stored_configs` 是启动时的整体入口（一个会话里先封配置行、再封审计历史、最后迁移本地模型密钥） | ✅ |
| `key_consolidation.py` | 核心 | 合并分裂的 providers 子键（defaultModelConfig/customModelInfo）到 providers bundle | ✅ |
| `onboarding.py` | 核心 | 首次配置 onboarding：检查状态、标记完成、推荐 provider、probe 本地模型与搜索（SearXNG/DuckDuckGo） | ✅ |
| `searxng_setup.py` | 辅助 | 本地 SearXNG 启动（Docker Compose，local/tauri deploy only）+ 启动后轮询探测可用性 | ✅ |

---

## 核心功能

### 1. 配置 CRUD (`service.py`)

**职责**：配置存取、同步、版本控制（乐观锁）。

**核心函数**：
- `set_config()`：写入配置（自动加密敏感字段）
- `get_config()` / `get_all_configs()`：读取配置（自动解密）
- `sync_configs()`：批量同步（含版本冲突检测；内容相同则幂等接受）
- `_apply_runtime_effects()`：提交后让配置的运行时副作用生效（`personalSettings` → 重新发布 harness 进程级隐私策略；`set` / `delete` / `sync` 共用写入口，因此 PUT、`/config/sync`、回滚都覆盖）
- `_encrypt_if_sensitive()`：写入前条件加密（含双重加密防护）
- `_decrypt_with_status()`：读取后解密，返回 `(值, unreadable)`（含旧 key fallback 迁移 + 双重加密修复）；`_decrypt_if_needed()` 是只取值的薄封装

**解密 fallback 机制**：
1. 当前 key 解密 → 成功则返回
2. 如果失败，尝试 legacy device-fingerprint key → 成功则记录 WARNING 日志
3. 双重加密检测：解密后如果仍是 `{"_cipher": "..."}` 结构，自动再解密一层
4. 全部失败（封存它的密钥已丢失）→ 值为 `{}`，`ConfigRecord.unreadable = True`。`{}` 与「从未保存」「保存的就是空」无法区分，所以靠这个显式标志：前端据此不把默认值回写覆盖该行并提示用户，远程备份调度据此不把它当成未配置

### 2. 加密策略 (`encryption.py`)

**职责**：业务层加密决策（何时加密、用什么 key）。

**密钥来源**：
- **Sandbox 模式**：`settings.config_encryption_key`（控制平面提供）
- **Local 模式**：`resolve_local_encryption_key(state_dir)` → 优先 env var `CONFIG_ENCRYPTION_KEY` → 文件 `{state_dir}/.encryption_key` → 自动生成

**敏感配置范围**：
```
providers, retrieval, searchServices, mcpServers, backupSync, voice, privacyRoutingSecret, externalAgents, egress_proxy, llm_proxy,
feishuCredentials, dingtalkCredentials, slackCredentials, ...
```

名单是手写的：`tests/services/config/test_config_key_classification.py` 要求每个 `ConfigKey` 要么在名单里、要么在该测试的「不含密钥」清单里，新增配置键而不表态会让测试失败。用户自己的本地模型端点的密钥单独存放在 `privacyRoutingSecret` 行（`{localApiKey}`，封存，口令归档下携带），不放进 `personalSettings`：偏好行因此不含任何密钥，是普通数据，它的审计历史与不带口令的归档都不会带出密钥。

### 3. 配置迁移 (`migration.py`)

**职责**：自动迁移明文配置到加密格式。

**执行时机**：应用启动时，`lifespan` 在 Local、Tauri、沙箱模式下都调用 `seal_stored_configs`（沙箱写入同样封存，库里仍是明文的行也要过这一遍；不加密配置的模式没有可封存的行）。幂等操作；失败只记警告，不阻塞启动。

**审计历史同样封存**：`config_audit_logs` 逐次重复保存过的值（`ConfigService.set` 写入时与主行同形，敏感键为 `{"_cipher": ...}`）。键在被列为敏感之前留下的明文旧值，由 `migrate_config_history_to_encrypted` 在同一时机补封；已封的值与非敏感键的历史原样保留，第二次运行不改任何行。

**本地模型密钥迁移**：`move_privacy_routing_key` 把仍存在 `personalSettings.privacyRouting.localApiKey` 的密钥搬进封存的 `privacyRoutingSecret` 行（该行已存在时以它为准），并从当前偏好与每条 `personalSettings` 审计快照里移除该字段。偏好行换新版本号，仍持有旧值的客户端会走冲突解决而不是把密钥写回。整个迁移是一个事务：失败不改任何行，第二次运行无事可做。

**不变量**：
- `migrate_configs_to_encrypted` 写入密文的同时置 `is_encrypted`——读取按这个标志而不是按值的形状判断是否解密，漏置时读回的是 `{}`。
- 已封的行不再封第二次：裸密文字符串与 `ConfigService` 写入的 `{"_cipher": ...}` 信封都原样跳过，否则值会被埋进第二层（读取侧与整实例归档仍能解开，但第二层是无谓的嵌套）。

### 4. Onboarding (`onboarding.py`)

**职责**：首次配置引导流程与本地模型/端点解析。

**核心函数**：
- `get_ollama_base_url()`：Ollama 基础端点解析 SSOT（支持 `OLLAMA_BASE_URL` / `OLLAMA_HOST` / `OLLAMA_HOST_URL`，自动协议补全，NAS 容器内打通宿主机）
- `check_onboarding_status()`：检查用户是否已完成首次配置
- `complete_onboarding()`：标记首次配置完成
- `get_recommended_providers()`：返回推荐 provider 列表（Ollama/OpenAI/Anthropic）
- `probe_local_models()`：并发探测本地模型服务（Ollama, LM Studio:1234），返回可用性、模型列表和延迟

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
