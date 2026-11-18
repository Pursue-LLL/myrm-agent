# tests/services/migration 模块架构

---

## 架构概述

外部助手数据迁移业务层回归测试。覆盖各来源的 discover/load/split、e2e dry-run、instruction rollback、skills binding、MCP 与 Hermes cron 转换、转录本会话车道、`.usage.json` sidecar 导入。与 `tests/architecture/test_migration_source_closure.py` 互补：本目录测行为，architecture 测 probe/loader 封闭集合同步。

上级：`app/services/migration/_ARCH.md`（Wizard 本机 6 源 + ZIP 通道的封闭集合政策）。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `test_source_discovery.py` | 核心 | Hermes / Claude Code / OpenClaw / Codex / Pi 的 filesystem discover（confidence、多源共存、edge cases；`has_importable_keys` 只认 `.env` 里能导入的 key，auth.json 与只含不支持变量的 `.env` 不算） |
| `test_source_manifest.py` | 核心 | 迁移来源 manifest SSOT（ids、import map、local-scan 封闭集、payload 结构） |
| `test_source_payload_loader.py` | 核心 | load_source_payload / build_coverage_items；Hermes 的 key 名按来源标记（`.env` 为 env，凭证池为 auth） |
| `test_source_payload_split.py` | 核心 | instruction vs memory 车道拆分；`has_api_keys` / `has_importable_keys` 的判断；Claude / Codex / Pi / Cursor 设置文件进入全局补充时不带凭证（任何片段都不留；`env` / `headers` 只留变量名；含凭证的字符串整体替换），不含凭证的设置仍可读，没有设置文件时不加设置块 |
| `test_migration_source_coverage.py` | 核心 | import source 映射、auto 路由回归、manifest 封闭集合 |
| `test_migration_e2e.py` | 核心 | discover → dry-run 端到端（hermes/openclaw） |
| `test_loaders_openclaw_extended.py` | 辅助 | OpenClaw 多 workspace / sessions loader 分支 |
| `test_loader_utils.py` | 辅助 | `_loader_utils` 共享函数 |
| `test_source_model_migrator.py` | 辅助 | 模型迁移的纯函数部分：路由 id 拆成 provider + model；`extract_hermes_auxiliary_config` / `extract_openclaw_default_model_config` 只留迁移读取的字段，缺失或畸形的 agents 块返回空 |
| `test_source_model_migrator_writes.py` | 辅助 | Hermes auxiliary + OpenClaw default model 的写入逻辑（配置服务替身与真实签名一致，漏传 `device_id` 会直接失败）；routing 仅 migrated_slots 非空时启用 |
| `test_migration_config_writes.py` | 核心 | confirm 改的三个配置行（providers / mcpServers / personalSettings）在真实配置服务 + 内存库上的行为：写入者记入审计；MCP 并入运行时读取的 `{"mcpConfigs": [...]}`、默认 disabled、用户已有项与其他键保留、全部已存在时不写；因密钥丢失解不开的行不被覆盖；全局指令合并与回滚；写入后下一次 `load_user_configs()` 读到新值 |
| `test_source_secrets_importer.py` | 辅助 | opt-in API key 导入：已有行（id 或 routingProfile 匹配）直接填 key 并带 expected_version、单凭 key 即可用的 provider 才新建行、多端点 provider 记为 needs_endpoint 且不写入、没有对应 provider 的变量按名列出，结果不含值，仅本机/Tauri 可用 |
| `test_env_secrets.py` | 辅助 | 迁移预览、payload key 名与导入三处读同一份 `.env` 时对「什么算 key」的结论一致（export 前缀、带注释的引号值、别名、空值、`${…}` 引用、缺文件）；没有对应 provider 的 key 变量名按文件顺序列出；payload 的 key 名带来源标记；`MULTI_ENDPOINT_PROVIDERS` 是 `IMPORTABLE_PROVIDERS` 的子集 |
| `test_import_archive_dry_run.py` | 辅助 | import archive dry-run 编排 |
| `test_lane_previews.py` | 辅助 | 四车道 preview DTO；凭证车道按「无 key / 可 opt-in 导入 / 只能手动填写 / provider 未就绪」给出提示 |
| `test_instruction_rollback.py` | 辅助 | 指令车道回滚 |
| `test_skill_binding.py` | 辅助 | 技能审核后 agent 绑定 |
| `test_workspace_bind_candidates.py` | 辅助 | OpenClaw migration workspace bind 候选路径 + fingerprint |
| `test_assistant_memory_loaders.py` | 核心 | Claude Code / Codex / PLUR 记忆车道的 probe 与 loader：Claude 自动记忆与指令分离、索引仅作兜底、自定义 `autoMemoryDirectory`、dry-run 导入记忆车道；沙箱 payload 只读取上传根目录内的文件 |
| `test_pi_migration.py` | 核心 | Pi 来源的 probe 与 loader：AGENTS.md / sessions / skills / auth 的 discover，auth 读成 env key 名（来源标记 auth，不算可导入），会话边缘情形（空文件、坏 JSON、非会话头、非消息条目、列表内容块拼接），指令计划 |
| `test_codex_obsidian_vault_hints.py` | 辅助 | Codex 迁移的 Obsidian vault 线索：从 settings 嵌套键提取 vault 路径、`load_codex` 产出线索、workspace bind 候选、扫描附近 vault |
| `test_session_lane.py` | 辅助 | `SessionMigrationService` 预览与确认落库（Chat / Message 表）；Claude / Codex / Hermes 转录本加载 |
| `test_mcp_config_converter.py` | 辅助 | 其他助手的 MCP 配置转换：Hermes stdio 与 tool filters、远程 keepalive 保留与过小忽略、`http` 别名映射 `streamable_http`、显式 `hostSerial` 优先于并行标志、布尔值不覆盖默认、Claude SSE、无效条目跳过；配置 dict 与预览输出 |
| `test_hermes_cron_converter.py` | 辅助 | Hermes cron 迁移转换：schedule 映射、忽略源模型字段、跳过无 agent 脚本的任务、跳过项预览行、从根目录读取 jobs、loader 带出 cron 计划、readiness 的 Hermes 门控告警 |
| `test_usage_sidecar_import.py` | 辅助 | Hermes `.usage.json` sidecar：读取与容错、字段映射为 `.stats.json`（状态与计数容错）、技能迁移写入账本且不覆盖已有账本、已有技能缺账本时补种 |
| `test_usage_sidecar_integration.py` | 辅助 | `.usage.json` 端到端：载入技能 payload → 写 `.stats.json` → harness 的 `SkillStatsCollector` 读取一致；部分命中只给匹配技能账本，curator 不把迁入技能判为陈旧（有计数无时间戳、pinned 豁免），数组形 JSON 与超大计数容错 |

---

## 依赖关系

- `app.services.migration.*`
- `app.services.memory.imports.import_adapters`
- `app.database.models`（会话车道落库）
- `myrm_agent_harness`（cron 类型、技能 `.stats.json` 账本与 `SkillStatsCollector`、转录本类型）
- `tests/architecture/test_migration_source_closure.py` — 结构闭包（非本目录）

---

## 运行

```bash
uv run pytest tests/services/migration/ -q
```
