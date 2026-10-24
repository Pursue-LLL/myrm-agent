# Myrm Agent Harness 框架设计原则

> **定位**：`myrm-agent/myrm-agent-harness/` 是业务无关的底层执行引擎与编排框架，随 `myrm-agent`（MIT）仓库分发。
> **许可**：MIT，见 `LICENSE`。PyPI 包名 `myrm-agent-harness`。

任何对本目录的改动都必须满足下列约束。与代码不一致的条款以 **§8 已知偏离** 为准：缺口在补齐前不得当作已生效的规则引用。

## 1. 框架与业务分离

- **零业务规则**：不含用户体系、计费、渠道校验、多租户调度。
- **零反向依赖**：`src/myrm_agent_harness/**` 只允许 import 自身与第三方包。`myrm_agent_server` / `myrm_control_plane` / `app` 前缀被 `scripts/boundary_config.py` 的 `BANNED_PREFIXES` 硬拦截，由 pre-commit `harness-boundary-check` 与 CI `harness-boundary.yml` 全量执行。
- **核心依赖 24 项**：`[project].dependencies` 只有 24 个运行时包，由 `tests/architecture/test_core_dependencies.py::test_core_dependency_count_is_stable` 锁定。浏览器、Qdrant、检索、OCR、FastAPI 宿主适配全部是 optional extras；harness 源码不 import `fastapi`。
- **契约优先**：跨层扩展点用 `Protocol` 或 Pydantic 模型定义（`api/protocols.py`、`api/hooks.py`、`toolkits/**/protocols.py`）。业务系统实现契约，框架不反向读取业务文件。
- **单实例、单用户**：一个 agent 实例服务一个用户；多用户靠多进程 / 多容器 / 多实例横向扩展。框架内不得引入租户隔离、跨用户共享状态或隐式 `user_id`。

## 2. 类型与代码质量

目标是 `mypy --strict` 全绿、`ruff check` 零告警；配置已就位（`pyproject.toml` 的 `[tool.mypy] strict = true` 与 `[tool.ruff.lint]`）。

当前实测（3191 个源文件）：

| 项 | 实测 |
|---|---|
| `mypy` | 2252 errors / 430 files |
| `ruff check src/` | 1331 errors |
| `Any` 注解 | 71 文件 / 198 处 |
| 缺返回类型注解 | 68 处（`no-untyped-def`） |

因此：

- 新增代码必须全量 Type Hints，不得引入新的 `Any`；确有必要时在同一行注释说明理由。
- 存量问题按「改到哪清到哪」处理；不得以「已开 strict」为据判断现有代码已合规。
- 类型与 lint **不在门禁内**：`.pre-commit-config.yaml` 的 7 个 hook 与所有 workflow 都不跑 mypy / ruff / pyright，违规不会被自动拦截。

## 3. 架构四不

1. **不为向后兼容留包袱**：不加 shim、不为改名保留旧名、不维护双份实现。
2. **不绕过持久化契约**：Memory / Artifacts / Checkpoints 走 `toolkits/storage` 的 `StorageProvider`、`ArtifactVault` 或 `runtime/checkpointing`；跨会话业务状态不得只存内存。
3. **不把大数据塞进 Prompt**：超阈值结果落 `ArtifactVault`，用 `vault://<uuid>` 指针传递（`agent/artifacts/vault.py` 的 `VAULT_PREFIX`）；禁止把千行文本拼进消息。
4. **不写偷懒实现**：核心调度必须具备并发与崩溃语义。SQLite 走 WAL 加固（`utils/db/sqlite/hardening.py`），文件写走 `infra.atomic_write`，子 agent 扇出受深度上限与并发闸门约束（`agent/sub_agents/manager.py` 的 `_MAX_GLOBAL_SPAWN_DEPTH = 3`、`runtime/concurrency_throttle/` 的分层信号量）。

## 4. 同沙箱零拷贝

`Agent-in-Sandbox`：主 agent、子 agent、bash、浏览器、文件系统同处一个隔离卷。大结果只在卷内落盘一次，agent 之间传 `vault://<uuid>`：

- Vault 位置：`{workspace_root}/.agent/vault`（`core/artifacts/paths.py` 的 `WORKSPACE_AGENT_DIR_NAME` / `ARTIFACT_VAULT_DIR_NAME`），可用 `AGENT_WORKSPACE_VAULT_RELATIVE` 重定位。
- 写入返回 `vault://<uuid>`（`agent/artifacts/vault.py` 的 `put_*`）；读取走 `file_read_tool` 或 `ArtifactVault.get`。
- 已接入该路径的两处：子 agent 超长输出（`agent/sub_agents/executor_helpers.py` 超限即 `put` 进 Vault 并返回指针）、MCP 超大响应（`toolkits/mcp/result_processing.py` 的 `OversizedResultHandler`，由业务层注入；未注入或失败时退化为头部截断）。matplotlib 图走的是另一套 `MyrmImage` 控制序列（`toolkits/code_execution/executors/common/wrapper_script.py`），不是 Vault 对象。

## 5. 分发与发布

**生效路径只有一条**：仓库根的 `.github/workflows/harness-publish.yml`。`harness-v<version>` tag → `scripts/verify_release_tag.py` 校验 tag 与 `pyproject.toml` 版本一致 → `uv build -o dist` → 干净 venv 装 wheel 跑 `verify-harness-distribution` → `uv publish`（OIDC）。

- 产物是**单个纯 Python wheel**，不剥源码：`uv build --wheel` 的包包含 `harness_packaging/core_manifest.yaml` 声明的全部 120 个叶子 `.py`。
- `verify-harness-distribution` 在源码完整时让 `runtime.install_guard.probe.get_distribution_mode()` 返回 `source`，`assert_distribution_ready()` 直接返回。它只证明「包能导入 + 公开 API 可解析」，不校验源码是否被剥离。
- **子目录 `.github/workflows/` 不生效**：GitHub 只执行仓库根的工作流目录，`myrm-agent-harness/.github/workflows/*.yml` 不会被触发。引用 CI 门禁时只认根目录的 workflow 文件。

**本地 / 手动双 wheel 工具链**（可运行，未接入 CI）：

| 组件 | 位置 | 作用 |
|---|---|---|
| 编译清单 | `harness_packaging/core_manifest.yaml` | 10 个目录 → 120 个叶子模块 |
| 元数据生成 | `scripts/sync_distribution_metadata.py` | 生成 `runtime/install_guard/_generated/core_ip_manifest.py` 与 `compiled-core` pin |
| 核心编译 | `scripts/build_core.py` | Nuitka 编译 + 平台 wheel |
| 发行剥离 | `scripts/build_release_wheel.py` | 从 wheel 删除清单内的 `.py` |
| 一键装配 | `scripts/assemble_production.py` | 串起两者，可 `--install` 到消费方 venv |
| 平台矩阵 | `harness_packaging/platforms.py` | 8 个 key（含 2 个 musl） |

使用前须知：PyPI 上 `myrm-agent-harness` 最新为 **0.1.0rc5**，而 `pyproject.toml` 已是 **0.1.0rc6**。`[compiled-core]` 与 `[compiled-core-musl]` 声明的 rc6 平台包均未发布，两个 musl 项目在 PyPI 不存在，装 `[compiled-core]` 会解析失败。

**公开面**：外部消费者只允许 `from myrm_agent_harness.api import ...`（`api/__init__.py` 的 `_EXPORTS` 惰性导出 + `api/__init__.pyi` 类型镜像，由 `tests/api/test_public_surface.py` 校验一致性）。其余子模块是内部实现，不构成兼容承诺。

## 6. 基础设施环境变量 vs Agent 配置

| 类别 | 配置方式 | 示例 |
|---|---|---|
| Agent 行为 | API / YAML / Pydantic | `AgentConfig`、`LLMConfig`、技能开关、`mcp_surface_mode` |
| 基础设施路径 | 可选环境变量，由部署层注入 | `MYRM_DATA_DIR`、`MYRM_PERSISTENT_ROOT`、`MYRM_LOCALES_DIR`、`MYRM_GATEWAY_*` |

框架不隐式读取 Agent 行为环境变量；`LLMConfig.from_env()` 与 `AgentConfig.from_env()` 仅在调用方显式调用时生效。

路径规则（按各模块实际实现；回退行为并不统一，改路径前先看该模块）：

| 变量 | 已设置 | 未设置 |
|---|---|---|
| `MYRM_DATA_DIR` | `{root}/checkpoints`（`agent/sub_agents/checkpoint/saver.py`）、`{root}/storage`（`toolkits/storage/config.py`）、`{root}/.estop_state.json`（`agent/security/guards/estop.py`）、`{root}/subagent_checkpoints.sqlite`（`agent/sub_agents/checkpointer.py`） | checkpoints 用 cwd 相对 `.myrm/checkpoints`；storage 与 estop 用 `~/.myrm` |
| `MYRM_PERSISTENT_ROOT` | `.context` / `.memories` / `workspace` 由它派生 | `/persistent` |
| `MYRM_LOCALES_DIR` | 覆盖诊断 i18n 目录 | 内置 `agent/errors/diagnostics/i18n/locales/`（de / en / ja / ko / zh-CN） |
| `MYRM_GATEWAY_URL` / `_TOKEN` | 第三方工具中继地址与凭证 | 不需要该能力时不必设置 |

`MYRM_PERSISTENT_ROOT` 必须每次调用时读取（`runtime/paths/execution_paths.py::get_persistent_root`），禁止在导入时快照成常量；部署层在启动之后设置也必须对所有调用方生效。消费方同样按调用时求值，不得缓存：bash 路径白名单取 `runtime/paths/execution_paths.py::get_context_root()`（`toolkits/code_execution/security/validator.py`），因此改根之后 `.context` 仍在该白名单内。

**框架边界**：不得硬编码 monorepo 路径，不得反向读取 `myrm-agent-server` 的文件。i18n、checkpoint、storage 必须自带默认数据或提供注入点（`register_translations()`、`StorageProvider`、checkpointer 工厂）。

## 7. MCP 工具暴露：只允许两个结局

MCP / OpenAPI 工具溢出只有两条路（`agent/_factory/mcp_routing.py`）：

| 结局 | 条件 | 模型侧表现 |
|---|---|---|
| **Direct FC** | 单服 schema ≤ `compute_direct_threshold()`（`FALLBACK_PTC_OVERHEAD_TOKENS` 450 × `PTC_OVERHEAD_MULTIPLIER` 25 = **11,250 tok**），且所有 direct 服合计 ≤ `AGGREGATE_DIRECT_TOKEN_BUDGET`（**15,000 tok**） | Turn1 给完整 JSON Schema，原生 `tool_call` |
| **MCP PTC** | 单服超 11,250 **或** 合计超 15,000（超限时按 schema 从大到小整服降级） | `skill_select_tool` → 在 `bash_code_execute_tool` 里写 Python；细节文档 `/mcp/{skill}/<func>.md` 用 `file_read_tool` 按需读 |

- `mcp_surface_mode=direct_fc` 强制 direct 并跳过合计降级（`agent/_factory/mcp_routing.py` 的 `MCP direct_fc override` 分支）。
- Direct FC 的 schema 预处理：描述截断到 2048 字符、`$ref` 内联、key 规范化排序（保 prompt cache 前缀稳定）、非规范 key 重命名、深层 schema 扁平化为点号路径、调用时反向还原；工具名统一加 `mcp__{server}__{tool}` 前缀。
- PTC 的三级渐进披露：L1 元数据 → L2 SKILL.md（带工具签名，超预算退化为仅列名）→ L3 单工具文档（`agent/skills/mcp/core_generator.py`）。
- **禁止第三路径**：`catalog_invoke` / `capability_invoke_tool` /「一个 invoke 工具代理所有 deferred MCP」/ RUNTIME 池 + Turn1 proxy gateway。`mcp_surface_mode=catalog_invoke` 会被解析成 `auto` 并打 WARNING（`agent/_factory/mcp_surface.py`）。
- **禁止第三档阈值**：11,250（单服）与 15,000（合计）之外不得再加灰色档位。
- 竞品可吸收的只有工程细节（连接稳定性、OAuth、stdio 生命周期、重试）；工具暴露模型与动作空间设计不引入。

**门禁现状**：`tests/architecture/test_mcp_routing_two_outcomes.py`（4 个断言）跑在 `harness-test.yml` 的全量单测里；该文件未打 `architecture` marker，`harness-boundary.yml` 的 `-m "architecture and not slow"` 会把它 deselect（实测 4 deselected）。63 个架构测试文件中有 16 个处于同样状态。

## 8. 已知偏离（规则已定，代码未达）

以下缺口是当前真实状态，引用对应条款前先确认是否已修复。

| 条款 | 偏离 | 证据 |
|---|---|---|
| §3 第1条 不留兼容包袱 | 24 个文件保留 `Backward-compatible alias` / `Legacy alias` | `core/security/egress/tainted_gateway.py`、`core/security/missing_semantics.py`、`toolkits/browser/pool/extension_bridge.py` 等 |
| §3 第2条 走持久化抽象 | 子 agent checkpoint 直接落文件系统，不经 `StorageProvider` | `agent/sub_agents/checkpoint/saver.py` 只用 `MYRM_DATA_DIR/checkpoints` + `atomic_write` |
| §3 第3条 / §4 零拷贝契约 | 两处产出 `ArtifactVault` 无法解析的指针：`vault://{chat_id}/turns/{i}/transcript.log`（从不落盘）、`vault://artifacts/{task}/result.json`（`default_worker_runner` 的模拟实现） | `agent/context_management/strategies/summary/turn_refetcher.py`、`agent/sub_agents/swarm_offload/offload_dispatcher.py`（该包在 `src/` 内无任何引用方，仅单测使用） |
| §5 发布一致性 | 发行 CI 不剥源码、不装 core 包；`[compiled-core]` 指向未发布的 rc6；musl core 项目不存在 | 根 `.github/workflows/harness-publish.yml` 只有 `uv build`；PyPI 最新 0.1.0rc5 |
| §2 类型目标 | 无 lint / 类型门禁；mypy 2252、ruff 1331 未清 | 见 §2 实测表 |
| §7 门禁覆盖 | MCP 双结局门禁未进入 `-m architecture` job | 见 §7 门禁现状 |

维护要求：修改框架行为、阈值、发布路径或门禁时同步更新本文对应条款。新增偏离要么修掉，要么在本表登记，不允许只在代码里悄悄存在。
