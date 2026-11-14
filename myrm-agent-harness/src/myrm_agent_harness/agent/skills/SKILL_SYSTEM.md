# 技能系统设计

> 技能系统的设计与实现说明；模块清单见 [skills/_ARCH.md](_ARCH.md)。

---

## 模块总览

| 编号 | 模块 | 分类 | 能力要点 |
|------|------|------|----------|
| 1 | 概述与设计目标 | — | 设计原则与模块职责 |
| 2 | 技能定义规范 | **CORE** | 名称/描述/条件激活与 frontmatter 校验 |
| 3 | 存储与发现 | **CORE** | 三层目录发现 + 信任分离 |
| 4 | 渐进式加载与 Prompt 生成 | **CORE** | 渐进式加载 + XML prompt + 摘要 |
| 5 | 信任模型与权限衰减 | **CORE** | 信任衰减 + 权限过滤 |
| 6 | 技能选择 | **CORE** | 受控的候选范围 + 模型选择 + 显式调用预加载 |
| 7 | 依赖检查与可用性 | **CORE** | 依赖探测 + 可用性门控 |
| 8 | 安全扫描框架 | **CORE** | 可扩展扫描规则 + 内容转义 |
| 9 | 安装与卸载 | **CORE** | 安全提取 + 隔离区安装（评分门禁、事务式回滚） |
| 10 | 状态管理 | **CORE** | 文件即真相：技能目录内的 `.stats.json` / `origin.json` / `receipt.json`；SQLite 快照 + 目录监听 |
| 11 | 技能失败事件 | **CORE** | `SkillFailureEvent` 交给宿主处置，框架本身不隐藏任何技能 |
| 12 | 搜索缓存 | **CORE** | 精确键 + TTL 的查询结果缓存 |
| 13 | Marketplace 集成 | ENHANCE | 多源 Marketplace 接入 |
| 14 | 技能创建与评估 | ENHANCE | AI 驱动的创建与评估 |
| 15 | 预置技能同步 | ENHANCE | 随版本发布的预置技能启动时同步到存储，三方哈希保护用户修改 |

> **CORE** = 技能系统的基础能力，**ENHANCE** = 可选增强能力。

---

## 1. 概述与设计目标

### 1.1 核心理念

技能（Skill）是 **"AI 的入职指南"** —— 将通用 Agent 变成特定领域的专家。

一个技能本质上是一份结构化的 Markdown 文档（`SKILL.md`），包含：
- **元数据**（YAML frontmatter）：名称、描述、依赖、信任级别等
- **指令正文**（Markdown body）：Agent 执行此技能时遵循的完整指令
- **辅助资源**（可选）：脚本、参考文档、模板等

### 1.2 设计原则

| 原则 | 说明 |
|------|------|
| **安全纵深** | 三层防御：信任衰减（硬限制）+ 安全扫描（软检测）+ 内容转义（注入防护） |
| **渐进式披露** | 只在需要时加载信息，最小化 Token 消耗 |
| **候选范围受控** | 模型只能在已绑定、可用、允许模型调用的技能里选择；选中后加载什么由框架决定 |
| **文件即技能** | 一个 `SKILL.md` 就是一个完整的技能定义 |
| **零代码扩展** | 纯 Markdown 即可创建技能，无需编程 |
| **协议驱动** | 通过 Protocol 抽象接口，支持多种后端实现 |

### 1.3 模块职责

| 模块 | 路径 | 职责 |
|------|------|------|
| `SkillBackend` Protocol | `backends/skills/protocols.py` | 存储抽象层 |
| `SkillMarketBackend` Protocol | `backends/skills/market_protocols.py` | Marketplace 抽象层 |
| `SkillWriteBackend` Protocol | `backends/skills/creation_protocols.py` | 技能写入抽象层（save/delete） |
| `SkillMetadata` 数据类 | `backends/skills/types/`（定义见 `types_metadata.py` 等） | 承载 trust、requires、tool 条件激活等字段 |
| `SkillRegistry` | `agent/skills/runtime/registry.py` | 集成信任模型和状态管理；XML 摘要（`get_metadata_summary`）经 `xml.sax.saxutils.escape` / `quoteattr` 转义 |
| `LocalSkillBackend` | `backends/skills/local.py` | builtin 层（Trusted） |
| `StorageSkillBackend` | `backends/skills/storage.py` | workspace 层（Trusted） |
| `CompositeSkillBackend` | `backends/skills/composite.py` | 路由层 |
| 信任衰减器 | `agent/skills/runtime/attenuator.py` | 按信任级别与 `allowed-tools` 过滤技能期间可用的工具 |
| 安全扫描器 | `backends/skills/scanning/scanner.py` | 多类别规则 + 严重级分类 |
| 技能选择 | `agent/meta_tools/skills/select/skill_select_tool.py` | 模型选择技能并加载 SOP；显式调用走预加载（见 §6） |
| 依赖检查器 | `backends/skills/prerequisites/` | 二进制/环境探测 |
| Frontmatter 验证器 | `backends/skills/_utils/`（`parse_skill_frontmatter`） | YAML 解析 + 字段校验 |
| 安装流水线 | `agent/skills/market/file_install.py`、`agent/skills/market/transaction.py` | 隔离区安装 + 事务回滚 |
| 安全提取器 | `backends/skills/scanning/zip_extract.py`、`agent/skills/market/installers/zip_installer.py` | zip 路径/大小/符号链接校验 |
| 使用与生命周期账本 | `backends/skills/stats_collector.py` | 技能目录内 `.stats.json` 的使用与生命周期统计 |
| 内容缓存 | `backends/skills/_content_memo.py` | 按内容复用扫描、解析与 token 计数结果（见 §10.3） |
| 搜索缓存 | `agent/skills/market/service.py`（`BaseSkillMarketService.search`） | Marketplace 搜索结果缓存（精确键 + TTL，见 §12） |

---

## 2. 技能定义规范 [CORE]

### 2.1 目录结构

```
skill-name/
├── SKILL.md          (必需) YAML frontmatter + Markdown 指令
├── scripts/          (可选) 可执行脚本 (Python/Bash/Node)
├── references/       (可选) 参考文档，Agent 按需读入上下文
└── assets/           (可选) 输出资源 (模板/图片/字体)
```

**设计决策**：
- 只支持 `SKILL.md` 作为入口文件
- 技能的唯一标识符是**目录名**（kebab-case），不是 frontmatter 中的 `name`

### 2.2 SKILL.md 格式

```markdown
---
name: my-skill
description: 简短描述，用于目录摘要和模型选择
version: 1.0.0
category: custom
requires:
  bins: [node, npm]
  env: [API_KEY]
  config: [~/.my-tool/config.json]
tags: [web, automation]
always: false
---

# 技能标题

## 指令正文
（Agent 加载此技能后读取的完整指令，建议 <500 行）
```

### 2.3 Frontmatter 字段完整列表

| 字段 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `name` | string | 推荐 | 技能名称（显示用，实际标识用目录名） |
| `description` | string | **必需** | 简短描述（≤1024 字符，超出截断；`<` `>` 被去掉），用于目录摘要和模型选择 |
| `version` | string | 可选 | 语义化版本号 |
| `category` | string | 可选 | 界面分组用的分类名 |
| `requires` | object | 可选 | 依赖声明（见 §7） |
| `requires.bins` | string[] | 可选 | 需要的 CLI 工具 |
| `requires.env` | string[] | 可选 | 需要的环境变量 |
| `requires.config` | string[] | 可选 | 需要的配置文件路径 |
| `tags` | string[] | 可选 | 分类标签；解析器识别该字段，Marketplace 搜索结果携带并按它匹配，不参与运行时技能选择 |
| `always` | boolean | 可选 | L1 token 预算内的优先排序；默认 `false`。**不保证一定出现，也不注入 SKILL.md 正文或 SystemMessage**（见 §4.3） |
| `model-invocable` | boolean | 可选 | 默认 `true`。为 `false` 时技能对模型隐藏，只能由用户触发；`disable-model-invocation`（取反）是等价写法 |
| `user-invocable` | boolean | 可选 | 默认 `true`。为 `false` 时技能不在前端展示，只能由模型自动选择 |
| `hooks` | object[] | 可选 | Hook 定义（事件触发）；只在用户显式调用该技能（`[use skill]` 或 `run(active_skill=...)`）的那一次运行里注册，模型自行加载的技能不会激活它们 |
| `allowed-tools` | string[] | 可选 | 允许使用的工具白名单（仅登记或已绑定的工具名生效，见下） |
| `allowed-domains` | string[] | 可选 | 出站网络请求允许的域名（DLP 防护）；未设置时不限制域名（SSRF 防护照常生效） |
| `required_permissions` | string[] | 可选 | 技能需要的权限（如 `file_write`、`shell_exec`）；安装时由用户批准，运行时强制执行，无效名称被跳过并告警 |
| `requires-tools` / `fallback-for-tools` | string[] | 可选 | 按智能体工具集条件激活：`requires-tools` 中任一工具缺席、或 `fallback-for-tools` 中任一工具在场时，技能对模型隐藏 |
| `requires-tool-groups` / `fallback-for-tool-groups` | string[] | 可选 | 同上，按工具组（`TOOL_GROUP_MAP`）判断 |
| `required-credential-files` | string[] | 可选 | 需要的凭据文件（相对工作区根目录）；加载时校验，缺失的记入 `missing_credentials` |
| `primaryEnv` | string | 可选 | apiKey 自动映射到的主环境变量名（如 `BRAVE_API_KEY`） |
| `oauth-issuer` / `required-oauth-issuers` | string / string[] | 可选 | OAuth issuer 键，限定运行时凭据注入的范围 |
| `required-mcp-server-ids` | string[] | 可选 | 预检所需的 MCP 服务器标识 |
| `evolution-locked` | boolean | 可选 | 为 `true` 时锁定自动进化 |
| `config-schema` | object | 可选 | 描述实例配置 `config_overrides` 的 JSON Schema 子集；存在时启用 schema 驱动的界面与校验 |
| `contract` | object | 可选 | 结构化契约，汇总进技能目录 |
| `scope_agent_id` | string | 可选 | 拥有该技能的智能体 id（多智能体作用域） |
| `specialized-model` | string | 可选 | 为该技能声明的专用小模型 / 领域模型 |
| `model-tier` | string | 可选 | 推荐的模型复杂度档位（`simple` / `standard` / `reasoning`） |
| `license` | string | 可选 | 许可证 |
| `compatibility` | string | 可选 | 环境要求（≤500 字符，超出截断） |
| `metadata` | object | 可选 | 扩展元数据；顶层的 `author`、`homepage` 并入其中 |

**命名规范**：
- 技能目录名：kebab-case，`^[a-z][a-z0-9-]*$`，最长 64 字符
- description：含 `<` `>` 角括号时去掉并告警，超过 1024 字符时截断并告警
- Frontmatter 字段：白名单验证，未知字段产生警告

**关键设计决策**：
- `requires` 采用结构化格式，包含 `config` 扩展，支持自动化检查
- `always` 只在技能数超过内联阈值时影响目录排序（token 预算内排在前面），不注入正文、不进 SystemMessage（见 §4.3）
- `allowed-tools` 是独占白名单：技能加载期间只保留所列工具。名称只有已登记（`is_registered_action_tool`）或本轮已绑定（如 MCP 工具）时才参与收窄；其他生态写法（`Bash`、`Read`、`Bash(ls *)` 等）无法对应任何 Myrm 工具，被忽略并在日志中按技能提示一次，声明里没有任何可识别名称的技能等同未声明。信任级别上限不受影响

---

## 3. 存储与发现 [CORE]

### 3.1 三层目录结构 + 信任分离

```
skills/
├── builtin/              # 内置技能（随项目发布，只读）→ Trust: Trusted
│   ├── memory/
│   │   └── SKILL.md
│   └── web-search/
│       └── SKILL.md
├── workspace/            # 用户本地技能（可读写）→ Trust: Trusted
│   └── my-custom-skill/
│       ├── SKILL.md
│       └── scripts/
└── installed/            # 外部安装技能（Marketplace/GitHub）→ Trust: Installed
    └── some-community-skill/
        └── SKILL.md
```

**优先级规则**：workspace > builtin > installed（同名技能，高优先级覆盖低优先级）

**信任分离**：
- `builtin/` 和 `workspace/` 中的技能自动获得 `Trusted` 信任级别
- `installed/` 中的技能自动获得 `Installed` 信任级别（受限）
- **物理目录决定信任级别**，无法通过 frontmatter 自行声明

**设计决策**：
- 采用三层方案 + 信任分离，比两层方案多一层安全保障
- `installed/` 层的技能受权限衰减约束（见 §5），只能使用只读工具
- 用户可以将 `installed/` 中信任的技能手动移到 `workspace/` 来提升信任
- builtin 对应 `LocalSkillBackend`，workspace/installed 对应 `StorageSkillBackend`
- 通过 `CompositeSkillBackend` 实现路由和优先级

### 3.2 存储抽象层

现有 `SkillBackend` Protocol 已提供完善的抽象，**无需修改**。

### 3.3 技能发现

现有 `SkillMarketBackend` Protocol 已定义搜索和安装接口，**无需修改**。

---

## 4. 渐进式加载与 Prompt 生成 [CORE]

### 4.1 四级加载策略

```
Level 0: 发现（Discovery）
  → list_skills() 返回所有技能的 SkillMetadata
  → 用于初始化时构建技能索引
  → 同时执行依赖检查和信任级别标注

Level 1: 摘要（Summary）
  → generate_skill_prompt() 生成安全 XML 摘要
  → 注入系统 Prompt，供 LLM 了解可用技能
  → Token 消耗：~50 tokens/技能

Level 2: 正文（Body）
  → get_skill_content() 返回 SKILL.md 正文
  → LLM 选择使用某技能后按需加载
  → Token 消耗：普通 skill 取决于作者文档；MCP L2 单 server ≤8,000 tokens（仅名称索引时 ≤3,000）
  → **MCP 例外**：`core_generator` 生成的 MCP SKILL.md 每个 server 有两档上限：带签名的 full / required 档 8,000 tokens，
    只列名称的 names 档 3,000 tokens（尾部截断而不是把提示词撑大）；
    fixed 前缀按实际 Header + Calling 动态计算，instructions 上限按 names 档推导，
    工具段用预算阶梯（full → required → names）适配工具数量，超限真正降级而不是只 warning。
    上限是单 server 的，不是多选 skill 的总预算。

Level 3: 资源（Resources）
  → get_skill_resources() 返回脚本/参考文档
  → 技能执行过程中按需加载
  → Token 消耗：按需
```

### 4.2 安全 XML 摘要格式

**当前格式：`get_metadata_summary()` 输出 `<skills>`；通用选择规则在 `skill_select_tool` 静态 description，L1 只负责目录与 hidden/search 动态规则。**

```xml
<skills>
  <skill name="mcp_12306_mcp_skill" available="true" trust="trusted" always="true">
    <description>该服务主要用于帮助用户查询12306的车票信息、特定列车的经停站信息以及相关的车站信息。</description>
  </skill>
</skills>
```

**关键安全措施**：
- 所有 XML 属性值经过转义（`<`, `>`, `&`, `"`, `'`）
- `<skill>` 标签逃逸检测（大小写不敏感，处理空白和 NUL 字节）
- 行尾规范化确保一致性哈希

**路由规则**：
- 通用规则在 `skill_select_tool` 静态 description，减少误触发；
- `trust` 属性让 LLM 知道技能的信任级别；
- L1 仅在有技能未内联（`hidden_count > 0`）时输出 search/hidden 动态规则；
- L1 按 `L1_CATALOG_MAX_TOKENS = 2,000` token 预算选择完整 `name + description` 条目，不再按技能个数截断；
- 预算外的技能不再只是一个数字：目录末尾的 `<hidden_skill_names>` 一行按字母序列出它们的名字（上限 `L1_HIDDEN_NAMES_MAX_TOKENS = 1,500`，超出时以 `and N more not listed` 收尾）。名字在目录里，模型直接 select；只知能力、不知名字才 search。
- 走 PTC 的 MCP 技能（服务器没有自带 instructions）在自己的条目里多一行 `<functions>`，按名字列出它的全部函数；目录里另有一个 `<function_index_rules>` 块，写明这类条目无需先 select，并给出调用约定（与 L2 正文共用 `agent/skills/runtime/ptc_calling.py` 的文本）。函数覆盖请求时，模型直接在 `bash_code_execute_tool` 里 `from skills.<name> import <函数>`，省掉一轮 `skill_select_tool`；需要全部签名时仍可 select。清单的预算 `L1_FUNCTION_INDEX_MAX_TOKENS = 1,200` 与条目预算分开计，不会挤掉其他技能的条目；一张清单要么整张列出要么不列（放不下时该服务器保持先 select）。服务器自带 instructions 时同样保持先 select，因为 instructions 只在 L2 正文里。

```xml
<skill name="mcp_kubernetes_skill" available="true" trust="trusted" always="true">
  <description>Kubernetes cluster operations: …</description>
  <functions>list_namespaces, get_namespace, list_pods, get_pod_logs, …</functions>
</skill>
```

### 4.3 Always 技能

`always: true` 的真实语义：**在 L1 token 预算内优先排序**（有 `skill_configs` 时同样先占预算，除非该技能被显式设为外围），不是“保证出现”。

**它不做什么**：

- ❌ **不**注入 SKILL.md 正文。L2 正文只在模型调用 `skill_select_tool` 后才通过 ToolMessage 返回（`core_generator.py` 的三级披露、`skill_document_loader.get_skill_document()`）。
- ❌ **不**写入 SystemMessage。目录块本身是 HumanMessage 的一段（`skill_catalog_delivery.py`），正文从不进 system prompt。

**真实分配行为**（`catalog_display.py`）：

```
model_visible = 可用且可调用的技能
候选          = 非空 skill_configs：显式 is_core 优先，未显式配置的技能仅在 always=True 时入选
                None 或 {}（同一种“未配置”状态）：全部 model_visible
排序          = always 在前，其后按名字
显示          = 按候选顺序放入完整 name+description，直到 L1_CATALOG_MAX_TOKENS（2,000）
hidden_count  = model_visible - 显示（它们的名字列在 <hidden_skill_names> 中）
overflow_count= 候选 - 显示（预算挤掉的候选；外围技能不算）
```

**后果**：

1. `always` 只是优先，不保证。MCP 由 `core_generator.py` 设 `always=True`，会优先占用预算（含已配置 `skill_configs` 的智能体）；预算耗尽后剩余 MCP 和用户技能只有名字出现在 `<hidden_skill_names>` 里。
2. 预算外技能有两种到达方式：名字已在目录里（或用户点名）→ 直接 `skill_select_tool`；能力已知、名字未知 → `skill_search_tool`。真实模型会话对照显示，有名字清单时检索往返显著减少、通过率无显著差别；代价是首次提示多出名字行的 token（130 个技能约 780）。
3. `skill_select_tool` 的白名单和 `skill_search_tool` 的索引都来自全量 `filtered_skills`；`hidden_count` 只表示“没有完整条目”，不表示“不可选”。

**如何被发现**：L1 完整条目 → 直接 select；`<hidden_skill_names>` 里的名字或用户点名 → 直接 select；能力已知/名字未知 → search（BM25 + jieba，MCP 工具名与 80 字符短描述也进索引）→ select。

**约束**：
- 建议 always 技能数量控制在 1-3 个。
- 典型 always 技能：memory（持久记忆）、core-policies（核心策略）。
- MCP 技能是例外：它们由生成器统一置为 `always=True`，不由 SKILL.md frontmatter 控制。

### 4.4 缓存策略

SKILL.md 由 `skill_document_loader.get_skill_document()` 按次从 backend 读取，backend 读取抛错时返回带错误提示的文档；已加载内容的前缀字节不变，**无需修改**。

---

## 5. 信任模型与权限衰减 [CORE]

### 5.1 信任级别

| 级别 | 目录 | 含义 |
|------|------|------|
| `Trusted` | `builtin/`, `workspace/` | 用户明确信任的技能，可使用所有工具 |
| `Installed` | `installed/` | 外部安装的技能，只能使用只读工具 |

### 5.2 权限衰减机制

**核心规则**：当多个技能同时激活时，**最低信任级别决定工具上限**。

```
场景 1: 只有 Trusted 技能激活
  → 所有工具可用

场景 2: 有任何 Installed 技能激活
  → 只有只读工具可用（read_file, list_dir, search, ...）
  → 写入工具被移除（write_file, execute_command, ...）
  → LLM 看不到被移除的工具定义（无法被 Prompt 注入绕过）
```

**只读工具白名单**（Installed 技能可用）：
- `read_file`, `list_dir`, `search`, `grep`
- `get_skill_content`, `list_skill_resources`

**关键安全特性**：
- LLM **看不到**被移除的工具定义，从根本上防止 Prompt 注入绕过
- 信任级别由物理目录决定，技能自身无法声明更高信任
- 用户可以通过移动技能目录来提升/降低信任

### 5.3 Agent 级别权限过滤

除了信任衰减，还支持 Agent 级别的技能可见性过滤：

- 不同 Agent 可以配置不同的技能权限
- `available(agent)` 方法根据 Agent 权限过滤可用技能列表
- 被 deny 的技能不会出现在 XML 摘要中

**设计决策**：
- 2 个信任级别足够覆盖所有场景（Trusted vs Installed）
- 最低信任原则从根本上防止权限升级
- 不采用更多级别（如  block/warn/off），因为硬限制比软警告更安全
- Agent 权限过滤是额外的细粒度控制层

---

## 6. 技能选择 [CORE]

模型选择技能；框架决定它能在哪些技能里选、选中后加载什么。

### 6.1 候选范围

- 进入目录（首条用户消息的 `<bound_skills>` 块）的技能必须已绑定、`available`（依赖与凭据满足）、`model-invocable`，并通过 `requires-tools` / `fallback-for-tools` 等工具条件。
- 完整条目在 token 预算内按「`always` 优先、名字次之」的顺序放入；智能体为技能配置了核心标记（`is_core`）时，以该标记决定谁拿完整条目（见 §4.3 与「L1/L2 缓存架构与降噪」）。
- 目录受 `L1_CATALOG_MAX_TOKENS` 约束，超出部分只列名字（`<hidden_skill_names>`）；能力已知、名字未知时用 `skill_search_tool`。

### 6.2 选择

- **隐式选择**：模型调用 `skill_select_tool(skill_names)`。首次加载返回完整 SOP；同一技能再次被选中只返回约 200 token 的摘要，同一次调用里重复写的名字也只加载一次。
- **显式选择**：用户用斜杠命令或命令面板触发时，消息形如 `[use skill_name] args`，`SkillAgent._preload_explicit_skill()` 把 SOP 直接注入查询，省掉一次模型往返；预加载出错时回退到隐式选择。

### 6.3 选中之后

- 信任级别与 `allowed-tools` 在技能加载期间限定可用工具（§5）。
- 选中记一次使用（技能目录内的 `.stats.json`，由 Curator 消费）；加载失败与缺失文件不记录。
- 完整流程见 [select/_ARCH.md](../meta_tools/skills/select/_ARCH.md)。

---

## 7. 依赖检查与可用性 [CORE]

### 7.1 依赖类型

| 类型 | 声明方式 | 检查方法 |
|------|----------|----------|
| CLI 工具 | `requires.bins: [node, npm]` | `shutil.which()` |
| 环境变量 | `requires.env: [API_KEY]` | `os.environ.get()` |
| 配置文件 | `requires.config: [~/.tool/config.json]` | `Path.exists()` |

### 7.2 检查时机

- **Level 0（发现）**：`list_skills()` 时执行依赖检查，结果缓存到 `SkillMetadata.available`
- **Level 1（摘要）**：XML 摘要中标注 `available` 和 `unavailable_reason`
- **Level 2（正文）**：不可用技能仍可加载正文（LLM 可引导用户安装依赖）

### 7.3 异步检查

所有检查异步执行，避免阻塞主流程：
- `bins` 检查通过 `asyncio.to_thread(shutil.which, ...)` 执行
- 结果缓存，不重复检查（除非手动刷新）

**设计决策**：
- 不可用技能不会从列表中隐藏，而是标注原因（LLM 可引导用户安装依赖）
- `config` 类型用于检查配置文件是否存在
- 异步检查确保大量技能时不阻塞启动

---

## 8. 安全扫描框架 [CORE]

### 8.1 架构

```
Scanner（编排器）
  ├── PatternAnalyzer（正则模式分析）
  ├── ContentSanitizer（内容转义）
  └── ScanPolicy（可配置策略）
```

### 8.2 威胁类别（27 类 117 模式）

| 类别 | 说明 | 模式数 |
|------|------|--------|
| `prompt_injection` | Prompt 注入攻击（含 DAN/jailbreak/HTML 注入） | 12 |
| `command_injection` | 命令注入 | 4 |
| `credential_exposure` | 凭据泄露（含 GitHub/OpenAI/Anthropic/AWS token） | 7 |
| `data_exfiltration` | 数据外泄（含 env dump/context exfil/markdown exfil） | 12 |
| `filesystem_access` | 敏感文件访问 | 5 |
| `process_operation` | 进程操作 | 4 |
| `network_access` | 网络访问（含隧道服务/paste 站点） | 7 |
| `screen_input` | 屏幕/输入捕获 | 2 |
| `memory_config_snooping` | 内存/配置窥探 | 4 |
| `code_injection` | 代码注入 | 4 |
| `privilege_escalation` | 权限提升（含 NOPASSWD/SUID） | 5 |
| `environment_manipulation` | 环境变量操纵 | 3 |
| `reflection` | 反射/元编程 | 3 |
| `deserialization` | 反序列化攻击 | 3 |
| `log_audit_tampering` | 日志/审计篡改 | 2 |
| `scheduled_task_injection` | 定时任务注入 | 2 |
| `container_escape` | 容器逃逸 | 2 |
| `memory_manipulation` | 内存操纵 | 2 |
| `dns_tunneling` | DNS 隧道 | 2 |
| `supply_chain` | 供应链攻击 | 5 |
| `obfuscation` | 代码混淆 | 7 |
| `destructive` | 破坏性操作 | 3 |
| `persistence` | 持久化（含 agent config 劫持） | 4 |
| `path_traversal` | 路径穿越 | 3 |
| `crypto_mining` | 加密货币挖矿 | 1 |
| `reverse_shell` | 反向 Shell | 5 |
| `prompt_secret_exfiltration` | Prompt 诱导泄露密钥 | 4 |

扫描器还包含 LLM 二次审计能力（可选），通过 `SkillLLMAuditor` 提供语义级威胁检测，遵循"只升不降"原则。

**设计决策**：
- 模式定义独立于扫描逻辑（`patterns/` vs `scanner.py`），便于扩展
- 扫描结果在进程内按「技能名 + 扩展名 + 内容 SHA-256」缓存（`ContentMemo`，见 §10.3）：内容一变就重新扫描，不跨进程持久化，重启进程后不会沿用旧扫描器的结论
- LLM 审计为可选增强，无 LLM 时 graceful fallback 到纯正则

### 8.3 内容转义

所有技能内容在注入 Prompt 前经过转义：
- XML 属性转义（`<`, `>`, `&`, `"`, `'`）
- `<skill>` 标签逃逸检测（大小写不敏感，处理空白和 NUL 字节）
- 行尾规范化（统一为 `\n`）确保一致性哈希

### 8.4 安装前扫描 + 用户确认

- 安装外部技能前自动执行安全扫描
- 如果检测到风险，暂停安装并提示用户确认
- 用户可选择：安装、安装但禁用、取消
- 待确认的安装有 TTL（5 分钟），超时自动取消

### 8.5 内容完整性哈希

每个技能的 SKILL.md 计算 SHA-256 内容哈希：
- 行尾规范化后计算（`\r\n` → `\n`），确保跨平台一致性
- 用途：白名单精确匹配、篡改检测、缓存失效判断、变更检测
- 哈希在加载时随 `SkillMetadata.content_hash` 一并计算（`backends/skills/_runtime.py::compute_content_hash`），不另存账本；预置技能同步、磁盘内容比对等需要判断变更的地方按当前内容重算后比较

### 8.6 白名单机制

- 已确认安全的技能可加入白名单（技能名 + 内容 SHA-256 哈希）
- 白名单中的技能跳过扫描
- 内容变更后哈希失效，需重新扫描

**设计决策**：
- 安全扫描是 CORE 而非 ENHANCE，因为这是生产级系统的底线
- 内容转义是独立于扫描的必要措施（即使扫描通过，也要转义）
- 白名单 + SHA-256 哈希确保效率和安全的平衡
- 行尾规范化确保跨平台一致性哈希

---

## 9. 安装与卸载 [CORE]

### 9.1 安装方式

| 方式 | 场景 | 信任级别 |
|------|------|----------|
| **目录复制** | 开发环境、本地技能 | Trusted（workspace） |
| **.skill 归档** | Marketplace 分发 | Installed |
| **Git URL** | GitHub/GitLab 仓库 | Installed |
| **Marketplace API** | 在线商店 | Installed |

### 9.2 隔离区安装流水线

所有来源（market 下载、LobeHub 模板、Agent Plugin 内的技能、业务层导入）都汇入同一条通路 `install_skill_files`（`agent/skills/market/file_install.py`）：`BaseSkillMarketService.install` / `install_from_url` 负责解析技能、下载并清洗文件（`sanitize_skill_files`），再交给它。

**进度回调**：调用方可传 `progress_callback(skill_id, stage, message)`。阶段依次为 `resolving → downloading → quarantine → scanning → installing → completed`；被门禁拒绝时为 `rejected`，解析或下载失败时为 `failed`。

**拒绝门禁**（按顺序执行，每一道都返回失败的 `SkillInstallResult`，不抛异常）：

| 顺序 | 门禁 | 错误码 |
|------|------|--------|
| 1 | 安装目录名必须是单个相对路径段（名称由发布方控制，防目录穿越） | `INVALID_SKILL_NAME` |
| 2 | 生命周期脚本门禁：`package.json` 的 `preinstall` / `install` / `postinstall` 非空即拒绝（§9.4） | `LIFECYCLE_SCRIPT_BLOCKED` |
| 3 | 安全评分低于 50 分 | `SECURITY_SCORE_BELOW_THRESHOLD` |
| 4 | 版本降级保护（`allow_downgrade=True` 可放行，§9.5） | `DOWNGRADE_BLOCKED` |
| 5 | 安装目标是符号链接 / junction，或是装着其他子技能的分类桶 | `PATH_REDIRECT_ATTACK` / `CATEGORY_BUCKET_COLLISION` |

**事务式提升**：文件先写入系统临时目录下的隔离目录（`skill-quarantine-*`），门禁全部通过后由 `SkillInstallTransaction.stage_replace` 复制到安装目录；目标已存在时先把旧目录快照备份，随后写入 `origin.json` 与 `receipt.json`（§10.1），最后 `commit` 清理备份。任何一步异常都回滚到旧目录的快照，新建的目录被删除；Agent Plugin 包内的技能与主目录在同一个事务里提升，要么全部生效，要么全部回滚。隔离目录在 `finally` 里一律删除。

**设计决策**：
- 门禁在提升之前执行；提升阶段才发现的拒绝（目标不安全）由事务回滚，被拒绝的包不会留下痕迹
- 先快照后覆盖，升级失败时用户的旧版本原样保留
- 评分通过但带有告警的技能照常安装，告警写入 `SkillInstallResult.scan_summary`，回执的 `security_verified` 记为 `false`
- 安装根是 `<状态根>/skills`（`LOCAL_INSTALL_DIR`）；安装流水线不决定信任级别，由宿主载入技能时赋予（§5）

### 9.3 安全提取

`.skill` 文件是标准 ZIP 归档，由 `safe_extract_zip`（`backends/skills/scanning/zip_extract.py`）在内存中解压，所有业务层共用这一个入口：
- 下载上限 50MB（`zip_installer.MAX_ZIP_SIZE`）
- 压缩比超过 100:1 视为 Zip Bomb 并拒绝；解压后总大小上限 50MB，条目数上限 4096
- 符号链接条目跳过；含 `..` 组件、以 `/` 或 `\` 开头、带 Windows 盘符前缀的条目跳过
- 含 ELF / PE / Mach-O 可执行二进制的成员，整个归档拒绝
- 解压结果交给 §9.2 的隔离区流水线（安全扫描见 §8）

### 9.4 package.json 生命周期脚本门禁

技能含 `package.json` 且声明了非空的 `preinstall` / `install` / `postinstall` 脚本时，安装前由 `check_lifecycle_scripts`（`backends/skills/scanning/package_audit.py`）判为 high 并直接拒绝（§9.2 门禁 2）；其他可疑的脚本命令只产生 medium 发现，进入 §8 的扫描结果，不阻断。安装流程本身不执行任何依赖安装命令。

### 9.5 版本比较与升级

- `backends/skills/versioning.py`：`compare_versions` 先按 `major.minor.patch` 比较，任一方不是语义化版本时退回字符串比较；`classify_version_bump` 把一次变更归为 initial / same / patch / minor / major / downgrade；`validate_version_guard` 在提升前拦截降级（§9.2 门禁 4）
- 搜索结果带 `installed_version` 与 `upgrade_available`（`BaseSkillMarketService._enrich_results`）
- `SkillAutoUpdateChecker`（`agent/skills/market/autoupdate.py`）惰性检查已安装技能，优先查询 `origin.json` 记录的来源，10 分钟冷却内复用上次结果；它只给出升级建议（`SkillUpdateInfo`），不原地改文件，`update_skill` 经 §9.2 的流水线重新安装

### 9.6 卸载流程

- 入口 `uninstall_skill`（`agent/skills/market/file_uninstall.py`）只接受 `local::` 开头的技能 ID，经 `resolve_local_install_dir` 映射到安装目录；其他 ID（如预置技能）直接返回失败
- 删除任何东西之前先过 `assert_safe_install_target`：符号链接 / junction / 越界目标整体拒绝，不会先删了子技能再失败
- 级联：安装根下 `origin.json` 的 `parent_plugin` 等于被卸载技能名、`skill_id` 相同，或被 `receipt.json` 的 `installed_skills` 列出的子目录一并删除；单个子目录删除失败只记警告，不中止
- 返回被删除的技能清单与原回执；启用 / 禁用、权限等宿主状态由宿主在卸载成功后自行清理（server 的做法：从启用列表移除，并清理该技能的权限数据）

**设计决策**：
- 回执（`receipt.json`）记录了装了哪些子技能，级联卸载不靠目录名猜测
- 卸载只动安装根，不碰用户自己放置的技能目录

---

## 10. 状态管理 [CORE]

### 10.1 文件即真相：状态随技能目录存放

技能没有集中账本。每个技能的状态就是它自己目录里的文件，复制、备份、删除技能目录时状态随之走：

| 文件 | 内容 | 写入者 |
|------|------|--------|
| `SKILL.md` | 技能定义与 frontmatter | 作者 / 创建服务 |
| `origin.json` | 来源 `source`、`skill_id`、`version`、`installed_at`；Agent Plugin 内的技能另有 `parent_plugin`，声明了 MCP 服务时有 `declared_mcp_servers` | 安装流水线（`agent/skills/market/helpers.py::write_origin`） |
| `receipt.json` | 安装回执：每个文件的 SHA-256 与大小、清单哈希 `manifest_hash`、`scan_score`、`security_verified`、`installed_skills` | 安装流水线（`agent/skills/market/transaction.py::write_receipt_file`），用于级联卸载与取证校验 |
| `.stats.json` | 使用计数（调用 / 成功 / 失败）、近期使用记录、`created_at`、`last_used_at`、生命周期状态（`active` → `stale` → `archived`）、`pinned`、`merged_into` | `SkillStatsCollector`（`backends/skills/stats_collector.py`），Curator 据此治理 |

另有实例配置与运行状态：`SkillStateManager`（`backends/skills/state_manager.py`）在 `.myrm/skills/instances/<技能>/<实例>.json` 与 `.myrm/skills/states/<技能>/<实例>.json` 下保存（默认相对工作目录）。

启用 / 禁用、各智能体可用的技能清单属于宿主状态，框架层不保存；server 把它们存在用户配置与 Agent profile 里。

### 10.2 原子写入与损坏处理

- `.stats.json`、实例配置与状态文件用 `infra.atomic_write.atomic_write` 写入：同目录 `mkstemp` 临时文件 → 写入并 `fsync` → `os.replace` 原子替换（跨设备时退回 `shutil.move`）→ 再 `fsync` 父目录；文件权限默认 `0600`
- `origin.json` 与 `receipt.json` 在安装事务内随目录一起提升，失败时整个目录回滚，不单独做原子写入
- `.stats.json` 读到无法解析的内容时改名为 `.stats.json.corrupt` 保留现场，再从空账本开始（创建时间取 `SKILL.md` 的修改时间）；读不出来（`OSError`）时绝不用空账本覆盖；纯读取从不写文件
- 账本不加锁：同一时刻两个写入方改同一个账本可能丢一次更新，调用方都在同一个事件循环里且读写之间不 `await`

### 10.3 列表每次读磁盘，派生结果按内容缓存

`LocalSkillBackend.list_skills` 与 `scan_workspace_skills` 每次都遍历技能目录并读取 `SKILL.md`，没有快照文件，也没有目录监听器：编辑、新增、删除在下一次列表里立刻可见，热重载不依赖任何后台线程，沙箱实例与桌面实例行为一致。`list_skills` 还会读取技能目录的 `.stats.json` 补上生命周期状态，已归档（`archived`）的技能不进入结果；工作区扫描不读取 `.stats.json`。

遍历的开销用「内容缓存」压下来：安全扫描（`scan_skill_content`）、frontmatter 解析（`parse_skill_frontmatter`）、token 计数都是文本的纯函数，结果由 `ContentMemo`（`backends/skills/_content_memo.py`）按文本缓存：

- 键 = 作用域 + 文本的 SHA-256，只存结果、不存文本；进程内、线程安全、最多 512 条（LRU），重启即空
- 不缓存：超过 64 KB 的文本、发现超过 128 条的扫描结果（防恶意文本撑爆内存）、抛出异常的计算（无效 frontmatter 每次都会重新报错）
- 返回的是独立副本：调用方改动返回的技能或扫描结果不会影响缓存
- 不缓存环境相关的结果：依赖检查（`check_requirements`：环境变量、PATH 上的命令）与凭据校验每次现算，装上命令或补全凭据后下一次列表就可用
- 副作用：同一内容的解析告警与 `Security scan:` 日志每个进程只出现一次

旧版本留在技能目录与项目目录里的 `.skills_snapshot.sqlite` 不再被读取，实例归档按文件名排除它。

### 10.4 热重载与性能

- **热重载 = 下一次列表重新读盘**：`SkillAgent._load_bound_skills` 总是向后端取列表、不做缓存，技能创建服务、市场安装与外部编辑器的改动在下一次取列表时生效，无需重启
- **重复列表的 CPU 耗时**（进程 CPU 时间，同一批技能重复列表，改动前后对照实测）：5 个技能 49.0ms → 1.0ms；20 个 210.2ms → 3.9ms；50 个 563.8ms → 7.3ms；134 个 1636.9ms → 20.5ms；首次列表不比之前慢
- 单个技能首次约 7–12ms（随 `SKILL.md` 体积），主要花在安全扫描与 frontmatter 解析上；内容不变之后只剩读文件与读 `.stats.json`

**设计决策**：
- 不做持久化缓存：持久化缓存要处理版本失效（扫描器升级后旧结论不能沿用）、序列化丢字段、清理过期条目，进程内缓存没有这些问题，而重复列表的收益已经拿到
- 不缓存任何依赖环境的结果：宁可多算一次，也不让「装好了却显示不可用」

---

## 11. 技能失败事件 (Skill Failure Event) [CORE]

### 11.1 默认行为：事件上报，不隐藏技能
技能归因的工具失败由 `_skill_failure_tracking` 中间件发布为 `SkillFailureEvent`（`runtime/events/skill_events.py`），由宿主决定如何处置（记录、触发 FIX 提案等）。中间件自身只把工具调用结果记入本次运行的技能使用记录（`backends/skills/usage_recorder`，不触发隔离或修复），因此默认栈不会把任何技能置为 `is_active=False`，也不会从技能列表中隐藏技能。

**计数口径**：仅当会话中恰好加载了一个存储技能时，每次工具调用的结果才记入该技能本次运行的使用记录：成功计成功；失败（排除 e-stop、hook 拦截、取消等策略性拦截，规则与失败事件一致）计失败；加载技能本身（`skill_select_tool`）不算结果。加载多个存储技能时归属不明，不计数。运行结束时每个用到的技能只落一条使用记录，写入 Curator 的 `.stats.json`（`SkillStatsCollector`，唯一的技能使用账本），结果按多数原则判定（失败调用超过一半才算失败，偶发且已恢复的错误不拖累技能）；没有归因到工具调用的使用只计使用次数、不计成败。因此成功率表示"有已观察结果的运行中的成功比例"；据此做决策的只有宿主审批流的 `low_effective_rate` 风险信号（已观察运行 ≥ 3 且成功率 < 50% 时该提案不得自动合并，转人工复核）；沙箱验证只留下验证记录。

---

## 12. 搜索缓存 [CORE]

### 12.1 查询结果缓存

`BaseSkillMarketService.search`（`agent/skills/market/service.py`）按查询词缓存聚合后的搜索结果：

- **缓存键**：小写并去掉首尾空白的查询词，精确匹配，不做相似度匹配
- **过期**：300 秒（`CACHE_TTL_SECONDS`）；命中时直接取缓存并按 `limit` 截断
- **容量**：最多 100 条（`CACHE_MAX_ENTRIES`），满了淘汰写入时间最早的一条
- **空查询**（浏览模式）：不查询任何源，返回空列表，同样进缓存
- 缓存只存原始搜索结果；「已安装版本 / 可升级」标记（§9.5）每次命中后重新计算，不进缓存
- 不加锁：缓存只在事件循环里读写

**设计决策**：
- 精确键 + TTL，不依赖近似匹配，命中行为可预测
- 已安装状态不进缓存，安装或卸载后的下一次搜索立即反映

---

## 13. Marketplace 集成 [ENHANCE]

### 13.1 多源聚合搜索

`BaseSkillMarketService` 聚合多个技能源的搜索。默认源：预置（prebuilt，宿主提供技能存储时才有）、静态索引（static_index）、ClawHub、GitHub、skills.sh、LobeHub、ModelScope、阿里云；宿主可用 `register_source` / `unregister_source` 增删自定义源。

**并发策略**：
- 对所有源并发发起搜索（`asyncio.as_completed`），逐个等待先返回的源，每次最多等 20 秒（`SEARCH_TIMEOUT`）
- 支持部分成功：超时或出错的源只记警告并跳过，已拿到的结果照常返回
- 各源结果先按来源优先级排序（`SOURCE_PRIORITY`：prebuilt > static_index > clawhub > skills_sh > github > lobehub，未列出的源为 0），再去重（`deduplicate`）、按查询词评分排序（`rank_results`）并截到 `limit`

### 13.2 统一 API

宿主 server 的实现，挂载在 `/api` 下：

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/skills/` | GET | 列出技能（含启用状态） |
| `/api/skills/discovery/search` | GET | 搜索 Marketplace |
| `/api/skills/discovery/preview` | POST | 安装前预览（含安全扫描） |
| `/api/skills/discovery/install` | POST | 安装技能（§9.2 流水线） |
| `/api/skills/discovery/install-from-url` | POST | 从 GitHub URL 安装 |
| `/api/skills/discovery/updates` | GET | 检查已安装技能的升级（§9.5） |
| `/api/skills/discovery/update` | POST | 升级技能 |
| `/api/skills/discovery/uninstall` | POST | 卸载技能（§9.6） |
| `/api/skills/{skill_id}` | GET | 技能详情 |
| `/api/skills/{skill_id}/files/{filename}` | GET | 读取技能文件（含 `SKILL.md`） |
| `/api/skills/local/toggle` | POST | 启用 / 禁用本地技能 |

### 13.3 多语言支持

- 技能描述支持 `description`（英文）和 `descriptionZh`（中文）
- 内置标签翻译表（110+ 标签）
- 前端根据用户语言偏好自动选择

### 13.4 GitHub 智能安装

- 智能 URL 解析：完整 URL、`owner/repo`、`owner/repo/path`、分支/标签/commit 引用
- 两级下载策略：GitHub Contents API（优先）→ `raw.githubusercontent.com`（降级）
- 多分支/路径模糊匹配搜索 `SKILL.md`

**设计决策**：
- Marketplace 是增强模块，不影响核心功能
- 并发搜索 + 查询结果缓存（§12）确保搜索性能
- 安装是异步调用，经 `progress_callback` 上报阶段（§9.2），不阻塞 UI

---

## 14. 技能创建与评估 [ENHANCE]

### 14.1 自动进化的触发源与审批闭环

自动进化由三类相互独立的触发源驱动，产出提案或成长记录，由服务端按风险决定自动落地或人工审核。

```
1. 触发源 (Triggers) →
   - 运行时失败（FIX）：Harness 把失败的工具调用归因到已加载的技能并发出 `SkillFailureEvent`；Server 的 `skill_immune_service` 做业务分类（配置、环境、瞬时故障只落拦截案例，不改技能）、按错误签名幂等去重，其余交给 `SkillEvolutionEngine.fix_skill` 起草修复。
   - 用户反馈与不满：用户在 GUI 里给技能提的反馈走 DERIVED 请求；Server 的不满路由（`frustration_routing.py`）在一轮对话结束后扫描对话，命中偏好类不满信号时，把提炼出的偏好作为技能补丁草稿交给 `process_skill_review_result` 进入用户审核，不经过进化引擎。
   - 后台复盘（新技能）：Harness 的复盘结果统一交给 `process_skill_review_result`：依次过锁定/已存在、CRITICAL 预检和高危新增复核，安全的新技能自动落盘，其余进入人工审核。
2. 失败轨迹 (Failure Trajectory，仅 FIX) →
   - `TraceAnalyzer.extract_trajectory(session_id, skill_id)` 读事件日志的末尾（聊天的日志含该聊天的所有轮次，限量读取只返回开头）：失败那个会话的概览、失败模式、工具统计、最近 20 条失败聚类后的错误、工具事件总数和最近 5 条工具事件（英文，约 1500 token 预算），再附上人类接管示范。技能全文不进轨迹：变体生成与评审各自完整接收技能正文，不再截断。
   - `session_id` 是事件日志的文件名。聊天的日志以聊天 ID 命名，Server 在调用前把失败事件里的会话键换成它，并要求结果是安全的文件名。
   - 读出的每个事件都再经一遍写入侧的脱敏，更早版本落盘的凭据不会进入提示词。
   - 没有以该键命名的日志文件时（无痕聊天不写日志；定时任务的日志按日分片，文件名带日期）返回空串，修复提示只带错误文本。
   - `TraceAnalyzer` 只在 `EvolutionIntegration` 拿到 `event_log_backend` 时创建；Server 运行时传入读取智能体事件日志目录的只读后端。
3. 零阻塞后台入队 (Zero-Blocking Dispatch) →
   - 入队的请求由后台 Worker 经 `EvolutionIntegration.evolve_skill` 先过 `EvolutionScreener`（锁定、冷却、静态拦截、FIX 的 LLM 确认），再交给进化引擎；主 Agent 继续对话毫无感知。
4. 提案与审批 (Proposal & Approval) →
   - 引擎产出 `EvolutionProposal`（FIX 与 DERIVED 先过 EvalCase 回归门，DERIVED 另过 Improvement Gate），不直接写库；Server 的 `ConfidenceApprovalFlow` 落地：运行时失败的修复一律人工审核，其余按置信度与风控信号决定自动合并或进入审核队列。
   - 引擎起草时读的是磁盘上的 SKILL.md（`evolution/core/skill_on_disk.py`）：编辑器、版本回滚和 agent 的技能工具改的是文件，不是进化库里的副本，基于副本的提案会在批准时覆盖技能已不再有的文本。文件与副本不同就以文件为准且不回写副本；文件大于进化库能存的上限（65,536 字符）时仍用副本。进化锁同样以文件为准：库里的标志或文件 frontmatter 里的标志任一为真即锁定，不受上述文本规则影响（文本相同、文件超限时照样读文件里的锁，读不到文件时读副本里的）。引擎运行期间文件又被改动的提案，Server 在落地前丢弃，下一次起草从新文件开始。
   - 前端 GUI 的审核收件箱亮起红点，等待用户显式批准。保护了系统 Prompt Cache 不被后台提炼静默击穿。
5. 拒绝反馈 (Rejection Feedback) →
   - 用户拒绝并给出理由时，理由写入该技能的进化约束；之后每次 FIX / DERIVED 起草变体，最近 5 条约束作为必须遵守的历史约束进入提示词，防止同一类废料被重复提出。
```

**设计决策**：
- 在后台进程全自动完成提取与重构，实现真正的无感进化，同时用沙箱预演和对抗性模糊测试彻底堵死知识库污染漏洞。
- 采用模糊匹配补丁机制（7级匹配策略），精准将 LLM 修改映射回 SKILL.md。
- 直接持久化到文件系统，部分替代依赖于通知系统的 Draft 草稿审批流，大幅提升真实系统的自动化自愈能力。

### 14.2 错误感知型智能拦截与 GUI-First 强制重试 (Error-Aware Static Interception & GUI-First Force Retry)

为了防止自动进化陷入“死循环”并优化 LLM 调用成本，系统在进化管线前端实现了轻量级静态拦截与 GUI 驱动的强制重试机制：

- **静态错误拦截 (Static Interception)**：在调用 LLM 确认错误前，通过正则表达式提取异常类型。如果检测到明确的语法或导入错误（如 `SyntaxError`, `ModuleNotFoundError`, `IndentationError`），则直接绕过 LLM 确认，允许进化（0 成本，极速响应）。
- **GUI-First 强制重试 (GUI-First Force Retry)**：默认情况下，进化失败的技能会进入冷却期（如 1 小时）。摒弃脆弱的多语言正则匹配，系统在前端“技能成长审计 (Evolution Rejection Dashboard)”提供明确的“强制重试”按钮。用户点击后，通过 API 传递结构化的 `force_retry=True` 标志，确定性地打破冷却锁，立即重试进化，实现防雪球与用户意图的完美平衡，且完全符合 GUI-First 原则。

### 14.3 技能进化锁定保护 (File-backed Evolution Lock)

为了解决真·自动进化机制可能带来的用户体验痛点（如：用户精心手动编辑修复的技能代码被后续基于错误反馈触发的自动进化覆盖），技能系统实现了**文件级双向进化锁定**架构。

**核心机制**：
- `evolution_locked`：一个布尔状态锁。该状态**直接作为 YAML Frontmatter 元数据** (`evolution_locked: true`) 存储在 `SKILL.md` 物理文件中。
- **文件即真相 (File-as-Truth)**：确保极客用户在本地离线修改或通过 Zip 分享技能时，锁状态伴随文件终身有效，避免由于仅存储在数据库中导致的脱节覆盖。
- **双向同步写入**：通过 API (`/skills/{skill_id}/evolution-lock`) 切换状态时，系统会同时更新 SQLite 缓存账本（用于极速查询）并物理复写 `SKILL.md` 的 YAML 头部。
- **EvolutionScreener 拦截 (双重纵深防御)**：
  1. **Phase 0 DB Check**：查询 SQLite 中 `store.is_evolution_locked`（极速零开销阻断，不读技能与文件）。
  2. **Phase 0 File Check**：`skill_from_disk` 把 SKILL.md frontmatter 里的锁并入技能（库里的标志或文件里的标志任一为真即锁定），防范文件被本地手动加锁、新建技能的锁只写进文件而数据库未同步的情况；强制重试只跳过冷却，不跳过锁；冷却看 `updated_at` 与拒绝历史，FIX 的 LLM 确认读的是这份磁盘文本。
- **引擎入口复核**：`derive_skill_simple` 与没有进化队列时的 `fix_skill` 不经过 Screener，在入口先经 `skill_from_disk` 取磁盘上的技能，再判一次锁。
- **两把锁，任一为真即锁定**：文件锁是 SKILL.md frontmatter 里的 `evolution-locked`（持久；宿主应用创建技能时可默认写入，用户也可手写）；库里的 `evolution_locked` 是 agent 经 `skill_manage lock/unlock` 设置的临时编辑保护，宿主应用也可经 `set_evolution_lock` 写同一个标志。`lock/unlock` 只写库、不写文件，所以 unlock 解除不了文件里的锁；文件里的锁还在时，unlock 的返回文本如实说明，不再回复「已重新启用」，是否移除由用户决定。
- **防覆盖保护**：不论是 FIX 还是 DERIVED 进化，锁定状态均作为防御纵深，确保持久化内容绝对不会被修改，将代码控制权完全交还给用户。

### 14.4 重复技能防御 (Duplicate Skill Defense)

随着技能数量增长，功能相似但名称不同的 skill 会不断累积（"Skill 熵增"），导致 Agent 变慢变笨。
系统不用嵌入向量判断技能相似度，靠创建前的 LLM 判断与创建后的整理器收敛：

**两道防线**：

```
创建前: reviewer prompt → 传入全量 skill 目录（名称 + 描述）→ LLM 自主判断转 patch 还是新建
创建后: curator 整并 → 按名字前缀聚类 → LLM 判官出整并计划 → 默认关闭，先预览再确认
```

**核心组件**：
- `agent/skills/evolution/review/reviewer.py`：复盘提示词带全量技能目录；已有技能能覆盖时给 `skill_patch`，没有才给 `skill_draft`
- `agent/skills/curator/consolidation/`：前缀聚类、判官、执行器（详见该目录的 `_ARCH.md`）

**设计决策**：
- 不阻断创建，最终决定权在 Agent 与人工审核
- 整并默认关闭，且一定先预览再确认
- 评审没成功的分组计入 `failed_clusters`；预览计划为空且有失败时报错（HTTP 502），不把失败说成「组织良好」，有动作时照常给出计划

### 14.5 多智能体技能池与按需加载 (Multi-Agent Skill Pool & On-Demand Loading)

在 Agent in Sandbox 架构下，每个用户拥有完全物理隔离的私有沙箱与持久化存储。智能体的技能管理遵循**私有技能池与按需配置**的极简原则。

**核心机制**：
- **沙箱私有技能池 (Sandbox Private Skill Pool)**：无论是用户批量导入的技能包，还是智能体自动提取进化出的技能，均统一保存在用户专属沙箱底层的技能库中。
- **零技能初始状态 (Zero-Skill Initialization)**：新建的智能体初始配置不包含任何技能（`AgentRuntimeSpec.skill_ids = []`）。底层 Factory 层严格遵循透传此配置，确保全新智能体以 0 技能启动，杜绝全局污染和提示词缓存命中率下降。
- **按需显式装载 (Explicit On-Demand Loading)**：多智能体的能力差异和隔离完全由配置驱动。用户在前端 GUI 为不同的智能体显式分配所需的技能 ID。运行时 `SkillAgent` 仅精准加载被显式选中的技能，实现能力的逻辑隔离。

**设计决策**：
- 坚持"奥卡姆剃刀"原则。智能体实例的 `skill_ids` 列表是定义其能力边界的唯一事实来源 (Single Source of Truth)。`scope_agent_id` 用于进化审核时标记技能的归属智能体（写入 frontmatter 和 SQL 查询过滤），但不影响技能的物理存储或全局池结构。
- 彻底拥抱 GUI-First，跨越智能体的能力复用与组合完全通过前端界面直观配置，所见即所得。

---

## 15. 预置技能同步 [ENHANCE]

### 15.1 设计

框架不内置技能清单：宿主把随版本发布的预置技能（`assets/prebuilt_skills/<skill>/SKILL.md` 及 `scripts/` 等附属文件）在启动时同步到存储。Server 的实现是 `app/core/skills/prebuilt_sync.py` 的 `sync_prebuilt_seeds`，由 lifespan 启动阶段的 `_init_prebuilt_skills` 调用，每个进程至多运行一次；同步失败只记 ERROR，不阻塞启动。

### 15.2 同步流程

1. 枚举种子目录，跳过以 `_` / `.` 开头的目录与没有 `SKILL.md` 的目录；frontmatter 无效的种子记 ERROR 并跳过。
2. 存储中还没有该技能：写入 `SKILL.md` 与元数据快照，并以种子内容的 SHA-256 记为 `origin_hash`。
3. 已存在则做三方哈希比较（种子 / 存储副本 / `origin_hash`）：
   - 副本未被改过：种子有更新就静默覆盖；
   - 副本被用户改过：保留用户副本，种子也变了则标记 `has_upstream_update=True`，前端据此提示"有上游更新"；
   - 旧快照没有 `origin_hash`：副本与种子一致就补写基线，否则保留用户副本并标记上游更新。
4. 附属文件（如 `scripts/`）始终跟随种子，不参与三方保护；快照里的 `requires` 与实际保留在存储里的 `SKILL.md` 保持一致，技能页与运行时按同一份依赖门控。
5. 种子目录里已移除的技能，其存储条目被清理。
6. 同步之后 `ensure_prebuilt_enabled_after_sync` 收敛启用状态：全新安装只启用默认技能集中当前仍存在的技能，既有安装保留用户的启用选择并清理已不存在的 id。

**设计决策**：
- 三方哈希保护用户对预置技能的修改，升级不会静默覆盖
- 同步幂等：重复启动不产生重复写入
- 同步失败不影响系统启动（降级运行）

---

## 附录 A: 设计决策汇总

| 决策 | 选择 | 备选 | 理由 |
|------|------|------|------|
| 信任模型 | 2 级（Trusted/Installed）+ 工具衰减 | 多级信任 / block-warn-off | 简洁且安全，硬限制优于软警告 |
| 技能选择 | 受控候选范围 + 模型选择 + 显式调用预加载 | 框架侧评分选择 | 候选范围由 `available` / `model-invocable` / 工具条件限定，选择交给模型，目录披露受 token 预算约束 |
| 安全扫描 | 可扩展的正则模式框架（27 个威胁类别）+ 可选 LLM 二次审计 | 仅 LLM 审计 | 正则快速、确定、无外部依赖；LLM 审计只升不降地补充语义级检测 |
| 内容完整性 | SHA-256 哈希 + 行尾规范化 | 无 | 白名单精确匹配、篡改检测、跨平台一致性 |
| 安装方式 | 隔离区流水线：评分门禁 + 事务式提升 | 直接解压覆盖 | 被拒绝的包不留痕迹，升级失败保留旧版本 |
| 搜索缓存 | 精确键 + 300 秒 TTL + 100 条上限 | 相似度匹配缓存 | 实现简单，命中行为可预测 |
| 状态持久化 | 技能目录内的 `.stats.json` / `origin.json` / `receipt.json`（`.stats.json` 原子写入） | 集中账本 / 数据库 | 随技能目录复制、备份与删除，没有集中状态可漂移 |
| 目录结构 | 三层 + 信任分离 | 两层 | 物理隔离确保信任级别不可伪造 |
| 摘要格式 | 安全 XML + 路由指令 | Markdown 表格 | 结构化、可嵌套、防注入 |
| 目录监听 | watchdog + SQLite 快照（`sync_all` 按 mtime 对账） | 仅 mtime 检查 | 实时性 + 一致性 |
| 内容安全 | XML 转义 + 标签逃逸检测 | 无 | 防止 Prompt 注入的最后一道防线 |
| 版本管理 | 语义化版本比较 + 升级提示 | 无版本管理 | 长期维护必备，用户不会错过重要更新 |
| 预置技能 | 随版本发布的种子（按需启用） | 强行装配 / 空白启动 | 遵循所见即所得：种子预置库供用户按需启用，内置通用智能体默认不加载技能（skill_ids = []，纯指令零启动基线） |

---

## 附录 B: 模块与代码位置

| 模块 | 代码位置 |
|------|----------|
| 技能定义规范 | `backends/skills/types/` 包（`types_enums`/`types_metadata`/`types_instance`/`types_visibility` 等） |
| 存储抽象层 | `backends/skills/protocols.py` |
| 发现抽象层 | `backends/skills/market_protocols.py` |
| 创建抽象层 | `backends/skills/creation_protocols.py` |
| 本地后端 | `backends/skills/local.py` |
| 存储后端 | `backends/skills/storage.py` |
| 组合后端 | `backends/skills/composite.py` |
| 技能注册表 | `agent/skills/runtime/registry.py` |
| 文档加载 | `agent/meta_tools/skills/select/skill_document_loader.py` |
| 元数据摘要（安全 XML） | `agent/skills/runtime/registry.py::get_metadata_summary` |
| 信任衰减器 | `agent/skills/runtime/attenuator.py` |
| 安全扫描器 | `backends/skills/scanning/scanner.py` |
| 内容转义器 | `agent/skills/runtime/registry.py`（XML 转义） |
| 技能选择 | `agent/meta_tools/skills/select/skill_select_tool.py` |
| 依赖检查器 | `backends/skills/prerequisites/` |
| Frontmatter 验证器 | `backends/skills/_utils/`（`parse_skill_frontmatter`） |
| 安装流水线 | `agent/skills/market/file_install.py`、`agent/skills/market/transaction.py` |
| 安全提取器 | `backends/skills/scanning/zip_extract.py` |
| 使用与生命周期账本 | `backends/skills/stats_collector.py` |
| 内容缓存 | `backends/skills/_content_memo.py` |
| 搜索缓存 | `agent/skills/market/service.py` |

---

## 附录 C: 不提供的能力

| 能力 | 不提供的原因 |
|------|--------------|
| 数据库存储 | 文件系统足够，状态随技能目录走 |
| 多租户 | 同上 |
| 完整安装历史 | `origin.json` 已有 installed_at/source，`receipt.json` 有文件清单，足够 |

## L1/L2 缓存架构与降噪 (L1/L2 Cache & Noise Reduction)

为了解决海量技能带来的上下文噪音（Context Noise）和“能力遗忘”（Capability Amnesia）问题，系统采用了 L1/L2 缓存架构：

1. **L1 核心技能 (Core Skills)**：
   - **机制**：`skill_configs.is_core=true` 的技能优先进入首条用户消息的 ``<bound_skills>`` 块（与 L2 同通道，由 ``resolve_catalog_display_skills()`` 解析；**不在** SystemMessage）。
   - **特点**：相对 L2 更高优先级出现在 catalog 内联列表，仍保持 ``skill_select_tool.description`` 字节稳定。
   - **适用场景**：用户在 GUI 标记为核心、对当前智能体高频使用的技能。

2. **L2 外围技能 (Peripheral Skills)**：
   - **机制**：将技能的 `name + description` 注入首条用户消息的 ``<bound_skills>`` 块，按 `L1_CATALOG_MAX_TOKENS = 2,000` token 预算截断；超出部分只列名字（`<hidden_skill_names>`，有独立的 token 上限），按名字 `skill_select_tool`，或能力已知、名字未知时 `skill_search_tool`。``skill_select_tool.description`` 保持字节稳定。
   - **注意**：不再按 20 个技能硬截断；预算外的技能以 `<hidden_skill_names>` 一行列出名字（不含描述）。
   - **特点**：极低 Token 消耗，0 认知负担。LLM 知道其存在，需要时通过 `skill_select_tool` 渐进式加载完整 SOP。
   - **适用场景**：低频使用、长尾技能。

### 精确 Token 成本计算
系统在技能保存/更新时，使用 `tiktoken` 精确计算技能 SOP 的 Token 消耗，并持久化到数据库中（`token_cost`）。前端利用此数据渲染“认知负载水位表”（Noise Gauge），帮助用户直观管理核心技能的负载。


## 技能同步 (Skill Sync)

跨设备/跨沙箱的技能双向同步，支持集体技能进化：

- **Protocol-first**: `SkillSyncProtocol` 定义传输接口，`SkillQualityGateProtocol` 定义推送质量门
- **增量同步**: `SkillSyncManifest` (SQLite) 追踪每个技能的 SHA256 和时间戳，避免全量比对
- **质量门控**: 只有满足最低执行次数和成功率的技能才会被推送到共享仓库
- **传输**：由宿主实现，框架只定义 `SkillSyncProtocol` 与质量门，不自带网络后端
- **后台执行**: 通过 `IdleTaskRegistry` 注册 `skill_sync` 任务类型，闲时自动触发
- **详细架构**: 参见 `agent/skills/sync/_ARCH.md`
