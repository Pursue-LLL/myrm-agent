# 技能管理系统设计文档

> 业务层：`app.core.skills` | 框架层：`myrm_agent_harness.backends.skills`

---

## 一、设计目标

构建**适配层**技能管理系统：

- **专注适配**：连接业务层和框架层，不实现存储细节
- **SKILL.md 规范**：符合 Claude 官方规范，单一配置文件
- **多存储后端**：Local / Storage(S3) / 业务层自定义

---

## 二、分层架构

```
app/api/skills/    API 路由
    ↓
app/core/skills/   业务适配层（本模块）
    ├── loader.py       SkillBackend 工厂
    ├── store/          CRUD / 池索引 / 用户配置
    ├── packaging/      打包 / 解包 / 校验
    └── providers/      本地提供者
    ↓
myrm_agent_harness.backends.skills/   框架层实现
    ├── LocalSkillBackend
    ├── StorageSkillBackend
    └── CompositeSkillBackend
```

---

## 三、核心流程

### 3.1 技能加载

```
SkillBackend.load_skills(skill_ids)
    → 解析 SKILL.md frontmatter
    → 返回 SkillMetadata 列表
```

### 3.2 技能发现与安装

```
discovery/    搜索外部源
    → sources/     MCP 源、市场源
    → installers/  安装流程编排
```

### 3.3 打包与解包

```
packaging/packer.py    目录 → 技能包
packaging/unpacker.py  技能包 → 目录
packaging/validator.py 校验包格式
```

### 3.4 预置技能种子（prebuilt_seeds）

```
prebuilt_seeds/{name}/SKILL.md   版本控制的工作流定义（YAML frontmatter + contract）
prebuilt_sync.py                 启动时同步到 storage + 清理幽灵条目
    → 写入 skills/prebuilt/{id}/SKILL.md
    → 写入 skills/prebuilt/{id}/_metadata.json（供 list_prebuilt_skills 发现）
    → 清理 storage 中已无对应 seed 目录的孤儿 SKILL.md 与 _metadata.json
user_config.ensure_prebuilt_enabled_after_sync()
    → 新用户：Catalog 默认空（enabled_prebuilt_ids = []）
    → 老用户：增量启用新种子（尊重 disabled_prebuilt_ids）；从 enabled/disabled 列表移除已无 seed 的 skill ID
builtin_initializer                  BuiltIn Agent 预绑定 default_skill_ids（is_core=false）
```

存储路径约定见 `myrm_agent_harness.toolkits.storage.paths`（`SKILL_METADATA_FILE = _metadata.json`）。

### 3.5 预置技能 vs Harness 工具（边界）

| 问题 | 答案 |
|------|------|
| 第三方 SaaS（Google/Notion/Linear）怎么用？ | **Skill** 编排 `web_fetch_tool` / `bash_code_execute_tool` / `http_request_tool`；或用户配置 **MCP** |
| 何时新增 harness `@tool()`？ | 仅当能力是**跨项目通用框架原语**（见 `toolkits/_ARCH.md`） |
| 预置 skill 上架条件 | `allowed-tools` 工具名正确（CI：`test_prebuilt_allowed_tools_match_tool_registry`）+ 依赖 OAuth/MCP **已在产品中可用** |
| 正例 | Google Workspace prebuilt skill + Settings OAuth GUI；`x-live-search` prebuilt skill + xAI provider + deferred `x_search_tool` |

Skill 是**业务能力**；Harness 工具是**框架能力**。禁止用 harness 工具实现单一厂商集成。

### 3.6 预置 skill  bundled scripts（bash 可执行）

| 步骤 | 说明 |
|------|------|
| Seed 同步 | `prebuilt_sync._sync_skill_bundle_files` 将 `scripts/` 等写入 storage |
| SKILL 命令 | 使用 `.claude/skills/{skill-id}/scripts/...` 全路径（含连字符 skill 名） |
| Runtime | `bash_executor` 检测路径 → `SkillWorkspaceManager` stage → cwd + token inject |
| OAuth scope | 集成 skill 的 SKILL.md frontmatter `oauth_issuer`（如 `google_workspace`）→ harness 解析为 `SkillMetadata.oauth_issuer` → bash 检测到 skill 路径时 `ExecutionContext.allowed_credential_issuers` 仅注入对应 issuer；generic bash（无 skill 路径）仍注入全部 session 凭证 |

### 3.7 Integration OAuth availability

| 步骤 | 说明 |
|------|------|
| OAuth 存储 | `app/services/integrations/oauth_store.py` — `oauthCredentials` 加密 blob |
| 判定 | `is_oauth_issuer_connected(db, issuer)` |
| Catalog | `apply_integration_oauth_availability` — `GET /skills/`、`GET /skills/{id}`、`GET /skills/available` |
| Agent runtime | `IntegrationOAuthSkillBackend` — `loader.create_skill_backend()` 外包；`skill_agent` 对 `available=false` 注入 SOP WARNING |
| 映射 | `INTEGRATION_SKILL_ISSUERS`（OAuth）、`INTEGRATION_SKILL_ENV_VARS`（Notion/Linear API key）、`INTEGRATION_SKILL_BINS`（xurl CLI）、x-live-search provider gate（`resolve_xai_search_config`） |
| Bash 注入 | `SessionCredentialAssembler` → `user_credentials_ctx`（Web / Channel / Cron / channel approval resume）→ harness bash env；详见 harness `SECURITY_DESIGN.md` §3.2.3 |
| GUI | Settings OAuth 卡 + Skills Catalog 黄标；x-live-search → `/settings/models`；保存 xAI provider 时 auto-enable skill |
| Write tier | `POST /oauth/start` `{tier: write}` 增量 consent；`write_enabled` on status API |
| Fail-closed | DB enrich 异常时 integration skill 标记 unavailable |

---

## 四、依赖关系

- **内部**：`app.core.storage/`（对象存储抽象）
- **框架**：`myrm_agent_harness.backends.skills`（SkillBackend Protocol）
- **被依赖**：`app.api.skills/`、`app.ai_agents/`

---

## 五、相关文档

- [skills/_ARCH.md](_ARCH.md) - 模块架构与文件清单
- [discovery/_ARCH.md](discovery/_ARCH.md) - 技能发现服务
- 框架层技能后端：`myrm_agent_harness.backends.skills`（PyPI `myrm-agent-harness`）
