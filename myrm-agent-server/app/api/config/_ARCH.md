# api/config 模块架构


---

## 架构概述

用户配置管理接口。支持配置的读取、更新、版本控制、按需加载和缓存失效。

---

## 文件清单

| 文件 | 地位 | 职责| I/O/P |
|------|------|------|-------|
| `router.py` | 核心 | 配置 CRUD、按需加载、版本管理、缓存失效、配置完整性检查、onboarding引导 | ✅ |
| `schemas.py` | 辅助 | 请求/响应 Pydantic 模型 | ✅ |
| `recovery_key.py` | 核心 | 加密恢复密钥管理（导出/导入，Local模式专用） | ✅ |

---

## API 接口

### 配置 CRUD
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config` | 获取配置，支持 `keys`（逗号分隔）、`sensitive` 过滤 |
| GET | `/config/{config_key}` | 获取单个配置 |
| GET | `/config/schema/{key}` | 获取 Omni-Config JSON Schema；`personalSettings` 字段含 `x-ui-section` / `x-ui-group` / `x-ui-visible-if` 元数据，供前端 SchemaForm 按 section 渲染 |
| PUT | `/config/{config_key}` | 设置配置（乐观锁：需提供 `expected_version`，冲突返回 409） |
| DELETE | `/config/{config_key}` | 删除配置 |
| POST | `/config/sync` | 批量同步（写入前复用 Omni-Config 全量校验；校验失败一次性返回 `validation_errors` 且不落库；支持部分成功，冲突写入响应体） |

### 配置完整性检查
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config/readiness` | 配置完整性（provider + search + onboarding），返回 is_ready / missing_items / suggestions |
| POST | `/config/onboarding/complete` | 标记用户首次配置完成（设置 User.config_completed_at） |
| GET | `/config/onboarding/recommendations` | 获取推荐的 provider 配置（Ollama/OpenAI/Anthropic），包含 pros/cons 和 setup_steps |
| GET | `/config/onboarding/probe-local` | 探测本地模型（Ollama/LM Studio）与搜索（SearXNG/DuckDuckGo），返回 `search_has_available` 与 `recommended_searxng_url` |

### 配置加密与恢复
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/config/encryption/recovery-key` | 导出加密恢复密钥（Local模式专用，用于硬件更换后数据恢复） |
| POST | `/config/encryption/recovery-key/validate` | 预校验恢复密钥（返回可恢复的配置数量，不执行实际落盘） |
| POST | `/config/encryption/recovery-key` | 导入恢复密钥（自动解密旧数据并使用新设备指纹重新加密） |

---

## 乐观锁机制

基于 `version` 字段的乐观锁控制并发修改：

### 后端实现
- **版本格式**：`timestamp_counter`（如 `1678901234_001`）
- **冲突检测**：客户端需提供 `expected_version`，服务端对比数据库中的 `version`
- **冲突响应**：返回 `409 Conflict` + `{"detail": "Version conflict", "serverVersion": "xxx"}`
- **批量同步**：`/config/sync` 先对全部变更执行同一套 Omni-Config 校验，任何校验失败都会返回 422 和全部 `validation_errors`，不会执行部分写入；版本冲突通过响应体 `conflicts` 返回。
- **版本递增**：每次成功修改后自动递增（新时间戳或 counter+1）

### 前端实现
- **ConfigSyncManager**：自动检测 409 冲突，在后台执行 **3-Way Deep Merge（三向深度合并）**。若非重叠字段修改，则自动合并并静默重试；若发生同字段冲突，则调用冲突解决器（`setConflictResolver`）。
- **冲突解决 UI**：`ConfigConflictDialog` 精美对话框（shadcn/ui），引入 `react-diff-viewer` 展示服务端与本地的 JSON **Visual Diff（可视化差异）**，用户清晰决策保留或放弃本地修改。
- **容错机制**：如果网络异常或重试失败，将变更安全压入离线队列，绝不静默覆盖本地数据，确保 100% 数据安全。
- **集成位置**：`settings-sync-initializer.tsx` 在应用初始化时注入冲突解决器。

**适用场景**：个人多设备访问（笔记本、平板、手机），防止配置覆盖。

---

## 缓存失效

配置变更（set/delete/sync 成功写入）后：
- 调用 `config_loader.invalidate_configs_cache()` 使 Channel Agent 等调用方立即读取最新数据
- 当 `config_key == "channels"` 时，额外调用 `SqlChannelPolicyProvider._invalidate_cache()` 使 DM/群聊策略立即生效

---

## 依赖关系

- `app/database/`：配置数据模型
- `app/api/dependencies.py`：认证依赖注入
- `app.core.channel_bridge.config_loader`：缓存失效（`invalidate_user_configs_cache`）
- `app.core.channel_bridge.channel_policy`：channels 策略缓存失效（`SqlChannelPolicyProvider._invalidate_cache`）
