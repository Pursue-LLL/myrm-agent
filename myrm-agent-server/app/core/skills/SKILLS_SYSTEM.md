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
    ├── store/          CRUD / 进化存储单例 / 用户配置
    ├── creation/       技能创作（SkillWriteBackend 本地实现）
    ├── packaging/      打包 / 解包 / 校验
    ├── providers/      本地提供者
    ├── discovery/      发现 / 采纳 / 挂载 / 上游更新
    ├── marketplace/    市场 / ClawHub 镜像 / 自定义源
    ├── gates/          集成凭证 / 权限 / 隔离 / 依赖 gate
    └── curator/        Curator 治理 / 技能合并（consolidation）
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
discovery/    搜索外部源（空 query 返回 []，需用户显式搜索）
    → sources/     MCP 源、市场源（ClawHub / ModelScope / Aliyun 等）
    → installers/  安装流程编排
marketplace/market_service  业务层：GitHub 源分析、自定义源、ClawHub 镜像懒加载、installed_skill_id 搜索 enrich
discovery/mount 安装/更新后 catalog enable 入口（prebuilt/local）
discovery/adopt   显式 agent.skill_ids 非空时，Discover install 自动 append 新技能（采纳契约）
marketplace/clawhub_registry UserSkillConfig.clawhub_registry_url → CLAWHUB_URL（运行时 SSOT）；bootstrap 迁移 OpenClaw legacy env；CN 预设 skill.xfyun.cn；legacy skillhub.cn 自动迁移；strict probe 验 ClawHub dict JSON
marketplace/clawhub_probe     切换国内镜像前 Block 0 可达性探测（GET /skills/discovery/registry-probe）
effective_skill_ids  解析 Agent 显式 allowlist（所见即所得标准：空名单装配 0 技能）；legacy local::{name} 读时迁移（全 local_skill_paths 根）
local_skill_id (harness)  local::{16hex} path-hash SSOT；install/uninstall/catalog 对齐
```

**契约与运维**：Agent 技能装配遵循所见即所得（WYSIWYG）原则，Agent 配置的 `skill_ids` 为空时运行时严格装配 0 个技能（纯指令模式）。默认通用智能体在出厂与启动初始化时显式写入全部预置技能。前端提供「全选」与「清空」快捷操作，支持按需一键装配。Discover install 在显式 allowlist 下会自动 append 新安装技能。

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
    → 新安装（无 config 文件）：默认不启动任何技能（enabled_prebuilt_ids = []，零启动纯净基线）
    → 已有配置：保持用户已选启用列表；从 enabled/disabled 列表移除已无 seed 的幽灵 ID
builtin_initializer                  BuiltIn Agent 默认不加载任何技能（skill_ids = []，纯指令模式）
```

存储路径约定见 `myrm_agent_harness.toolkits.storage.paths`（`SKILL_METADATA_FILE = _metadata.json`）。

### 3.5 预置技能 vs Harness 工具（边界）

| 问题 | 答案 |
|------|------|
| 第三方 SaaS（Google/Notion/Linear）怎么用？ | **Skill** 编排 `web_fetch_tool` / `bash_code_execute_tool`；或用户配置 **MCP** |
| 何时新增 harness `@tool()`？ | 仅当能力是**跨项目通用框架原语**（见 `toolkits/_ARCH.md`） |
| 预置 skill 上架条件 | `allowed-tools` 工具名正确（CI：`test_prebuilt_allowed_tools_match_tool_registry`）+ 依赖 OAuth/MCP **已在产品中可用** |
| 正例 | Google Workspace prebuilt skill + Settings OAuth GUI；`x-live-search` prebuilt skill + xAI provider + 沙箱标准脚本 PTC（**不依赖** Agent Web Search/Tavily，0 Action Tool 注册） |

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
| 映射 | `INTEGRATION_SKILL_ISSUERS`（OAuth）、`INTEGRATION_SKILL_ENV_VARS`（Notion/Linear API key、imap-smtp-email `EMAIL_IMAP_HOST`）、`INTEGRATION_SKILL_BINS`（xurl CLI）、x-live-search provider gate（`resolve_xai_search_config`） |
| Bash 注入 | `SessionCredentialAssembler` → `user_credentials_ctx`（Web / Channel / Cron / channel approval resume）→ harness bash env；详见 harness `SECURITY_DESIGN.md` §3.2.3 |
| GUI | Settings OAuth 卡 + Skills Catalog 黄标；x-live-search → `/settings/models`；保存 xAI provider 时 auto-enable skill |
| Write tier | `POST /oauth/start` `{tier: write}` 增量 consent；`write_enabled` on status API |
| Fail-closed | DB enrich 异常时 integration skill 标记 unavailable |
| Bin gate scope | `INTEGRATION_SKILL_BINS` 使用 server 进程 `PATH`（与 harness `check_requirements` 一致）；sandbox 内 CLI 可用性以运行时 bash 错误为准 |
| Env gate scope | `INTEGRATION_SKILL_ENV_VARS` 读取进程 env + `UserSkillConfig.skill_env_vars`（优于 harness 仅读 os.environ） |

### 3.8 Skill 权限管理链路

| 层 | 内容 |
|------|------|
| 声明 | SKILL.md frontmatter `required_permissions: [file_write, shell_exec, ...]`；未知权限名 fail-lenient（跳过 + WARNING） |
| 解析 | harness `parse_skill_frontmatter` → `SkillFrontmatter.required_permissions: list[SkillPermission]` → `build_skill_metadata` → `SkillMetadata.required_permissions` |
| 落库 | server `Skill.from_metadata` 映射枚举值到字符串；`Skill.required_permissions` 随 `to_dict`/`from_dict` 持久化 |
| API | `app/api/skills/permissions.py`：`GET /{skill_id}/permissions`、`POST .../grant`、`POST .../revoke`、`POST .../apply-template`、`POST /permissions/bulk-revoke-by-type`、`GET /{skill_id}/permissions/usage` |
| UI | 设置 → AI 工具 → 「权限管理」Tab（授予/撤销/批量撤销）；技能详情 → 「权限使用统计」区（允许/拒绝率 + 最近操作） |
| 运行时 | `SkillBoundaryProvider` guardrail 依据 `SkillPermissionGrant` 判断放行/拦截；操作写入 `skill_permission_usage_logs` |
| 卸载清理 | `SkillMarketService.uninstall` 成功后调用 `permission_service.purge_skill_permissions`：删除该 skill 的 `SkillPermissionGrant` + `skill_permission_usage_logs`，并清空内存权限缓存，防止重装同 ID 技能继承旧授权 |

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
