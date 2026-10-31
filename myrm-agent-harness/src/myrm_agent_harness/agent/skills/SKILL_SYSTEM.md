# 技能系统设计方案（集大成版 v2）

> 基于 myrm-agent-harness 现有架构设计的完整技能系统方案。
>
> 落地状态以本仓实现为准；见 [skills/_ARCH.md](_ARCH.md)。

---

## 模块总览

| 编号 | 模块 | 分类 | 核心来源 |
|------|------|------|----------|
| 1 | 概述与设计目标 | — | 全部 14 项目共识 |
| 2 | 技能定义规范 | **CORE** | OpenClaw + Deer-Flow + Nanobot |
| 3 | 存储与发现 | **CORE** | ironclaw 三层目录 + 信任分离 |
| 4 | 渐进式加载与 Prompt 生成 | **CORE** | ironclaw XML + LobsterAI 路由 + picoclaw 摘要 |
| 5 | 信任模型与权限衰减 | **CORE** | ironclaw 信任衰减 + opencode 权限过滤 |
| 6 | 确定性技能选择器 | **CORE** | ironclaw 评分 + 排除关键词 + Token 预算 |
| 7 | 依赖检查与可用性 | **CORE** | Nanobot + ironclaw gating |
| 8 | 安全扫描框架 | **CORE** | CoPaw 可扩展框架 + ironclaw 内容转义 |
| 9 | 安装与卸载 | **CORE** | Deer-Flow 安全提取 + 隔离区安装流水线（评分门禁、事务式回滚） |
| 10 | 状态管理 | **CORE** | 文件即真相：技能目录内的 `.stats.json` / `origin.json` / `receipt.json`；SQLite 快照 + 目录监听 |
| 11 | 技能失败事件与可选隔离读取 | **CORE** | `SkillFailureEvent` 交给宿主处置；`QuarantineAwareSkillBackend` 仅过滤宿主置为 `is_active=False` 的技能 |
| 12 | 搜索缓存 | **CORE** | 精确键 + TTL 的查询结果缓存 |
| 13 | Marketplace 集成 | ENHANCE | NextClaw API + CoPaw 多源 |
| 14 | 技能创建与评估 | ENHANCE | Deer-Flow AI 驱动 |
| 15 | Skill Packs 技能集合 | ENHANCE | NanoClaw Flavor + Clawith Template |
| 16 | Curated Skills 预安装 | ENHANCE | nexu |

> **CORE** = 必须实现（竞争力底线），**ENHANCE** = 可选增强。

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
| **确定性优先** | 技能选择不依赖 LLM，避免循环操纵 |
| **文件即技能** | 一个 `SKILL.md` 就是一个完整的技能定义 |
| **零代码扩展** | 纯 Markdown 即可创建技能，无需编程 |
| **协议驱动** | 通过 Protocol 抽象接口，支持多种后端实现 |

### 1.3 与现有代码的关系

本方案基于 myrm-agent-harness 现有架构，**保留已有优秀设计**，补充和增强：

| 现有模块 | 路径 | 方案中的角色 |
|----------|------|-------------|
| `SkillBackend` Protocol | `backends/skills/protocols.py` | **保留**，作为存储抽象层 |
| `SkillMarketBackend` Protocol | `backends/skills/market_protocols.py` | **保留**，作为 Marketplace 抽象层 |
| `SkillWriteBackend` Protocol | `backends/skills/creation_protocols.py` | **保留**，作为技能写入抽象层（save/delete） |
| `SkillMetadata` 数据类 | `backends/skills/types/`（定义见 `types_metadata.py` 等） | **已实现** trust、requires、tool 条件激活等字段 |
| `SkillRegistry` | `agent/skills/runtime/registry.py` | **增强**，集成信任模型和状态管理 |
| `get_metadata_summary()` | `agent/skills/runtime/registry.py` | **升级**，改为安全 XML 摘要格式 |
| `LocalSkillBackend` | `backends/skills/local.py` | **保留**，映射为 builtin 层（Trusted） |
| `StorageSkillBackend` | `backends/skills/storage.py` | **保留**，映射为 workspace 层（Trusted） |
| `CompositeSkillBackend` | `backends/skills/composite.py` | **保留**，作为路由层 |

**新增模块**：

| 新模块 | 包路径 | 核心来源 |
|--------|--------|----------|
| 信任衰减器 | `agent/skills/runtime/attenuator.py` | ironclaw |
| 安全扫描器 | `backends/skills/scanning/scanner.py` | CoPaw |
| 内容转义器 | `agent/skills/runtime/registry.py`（`xml.sax.saxutils.escape` / `quoteattr`） | ironclaw |
| 确定性选择器 | 未落地：由 `agent/meta_tools/skills/select/skill_select_tool.py`（模型选择技能并加载 SOP）承担 | ironclaw |
| 依赖检查器 | `backends/skills/prerequisites/` | Nanobot + ironclaw |
| Frontmatter 验证器 | `backends/skills/_utils.py`（`parse_skill_frontmatter`） | Deer-Flow |
| 安装流水线 | `agent/skills/market/file_install.py`、`agent/skills/market/transaction.py` | Deer-Flow + nexu |
| 安全提取器 | `backends/skills/scanning/zip_extract.py`、`agent/skills/market/installers/zip_installer.py` | Deer-Flow + nexu |
| 使用与生命周期账本 | `backends/skills/stats_collector.py` | 本仓 |
| 快照与目录监听器 | `backends/skills/snapshot.py`、`backends/skills/watcher.py` | nexu + LobsterAI |
| 搜索缓存 | `agent/skills/market/service.py`（`BaseSkillMarketService.search`） | 本仓 |
| XML 摘要生成器 | `agent/skills/runtime/registry.py`（`get_metadata_summary`） | ironclaw + LobsterAI + picoclaw |

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
- 只支持 `SKILL.md` 作为入口文件（14 个项目共识）
- 技能的唯一标识符是**目录名**（kebab-case），不是 frontmatter 中的 `name`

### 2.2 SKILL.md 格式

```markdown
---
name: my-skill
description: 简短描述，用于触发匹配和上下文摘要
version: 1.0.0
category: custom
requires:
  bins: [node, npm]
  env: [API_KEY]
  config: [~/.my-tool/config.json]
tags: [web, automation]
patterns: ["https?://.*\\.example\\.com"]
always: false
exclude-keywords: [unrelated-topic]
max-context-tokens: 8000
---

# 技能标题

## 指令正文
（Agent 触发此技能后读取的完整指令，建议 <500 行）
```

### 2.3 Frontmatter 字段完整列表

| 字段 | 类型 | 必需 | 说明 | 来源 |
|------|------|------|------|------|
| `name` | string | 推荐 | 技能名称（显示用，实际标识用目录名） | OpenClaw |
| `description` | string | **必需** | 简短描述（≤1024 字符），用于摘要和触发匹配 | 全部 |
| `version` | string | 可选 | 语义化版本号 | OpenClaw + CoPaw |
| `category` | enum | 可选 | `builtin` / `custom`，默认 `custom` | Deer-Flow |
| `requires` | object | 可选 | 依赖声明（见 §7） | Nanobot + ironclaw |
| `requires.bins` | string[] | 可选 | 需要的 CLI 工具 | Nanobot |
| `requires.env` | string[] | 可选 | 需要的环境变量 | Nanobot |
| `requires.config` | string[] | 可选 | 需要的配置文件路径 | ironclaw |
| `tags` | string[] | 可选 | 分类标签（用于搜索、过滤、选择器匹配） | NextClaw + ironclaw |
| `always` | boolean | 可选 | L1 token 预算内的优先排序；默认 `false`。**不保证一定出现，也不注入 SKILL.md 正文或 SystemMessage**（见 §4.3） | Nanobot |
| `hooks` | object[] | 可选 | Hook 定义（事件触发） | 现有架构 |
| `allowed-tools` | string[] | 可选 | 允许使用的工具白名单（仅登记或已绑定的工具名生效，见下） | 现有架构 |
| `patterns` | string[] | 可选 | 正则模式（精确匹配 URL/路径等格式） | ironclaw |
| `exclude-keywords` | string[] | 可选 | 排除关键词（防止误触发） | ironclaw |
| `max-context-tokens` | int | 可选 | 最大上下文 Token 数（默认 8000） | ironclaw |
| `license` | string | 可选 | 许可证 | agentskills.io |
| `compatibility` | string | 可选 | 环境要求（≤500 字符） | agentskills.io |
| `metadata` | object | 可选 | 扩展元数据（author、homepage 等） | agentskills.io |

**命名规范**（来自 Deer-Flow 验证器）：
- 技能目录名：kebab-case，`^[a-z][a-z0-9-]*$`，最长 64 字符
- description：禁止包含 `<` `>` 角括号，最长 1024 字符
- Frontmatter 字段：白名单验证，未知字段产生警告

**关键设计决策**：
- `requires` 采用 Nanobot 的结构化格式 + ironclaw 的 `config` 扩展，支持自动化检查
- `exclude-keywords` 和 `max-context-tokens` 来自 ironclaw，用于确定性选择器
- `always` 来自 Nanobot，但**语义已收窄**：它只在技能数超过内联阈值时保住目录可见性，不注入正文、不进 SystemMessage（见 §4.3）
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

**信任分离**（来自 ironclaw）：
- `builtin/` 和 `workspace/` 中的技能自动获得 `Trusted` 信任级别
- `installed/` 中的技能自动获得 `Installed` 信任级别（受限）
- **物理目录决定信任级别**，无法通过 frontmatter 自行声明

**设计决策**：
- 采用 ironclaw 的三层方案 + 信任分离，比两层方案多一层安全保障
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
  → Token 消耗：普通 skill 取决于作者文档；MCP L2 单 server ≤3,000 tokens
  → **MCP 例外**：`core_generator` 生成的 MCP SKILL.md 每个 server 上限 3,000 tokens；
    fixed 前缀按实际 Header + Calling 动态计算，instructions 上限由剩余预算推导，
    工具段用预算阶梯（full → required → names）适配工具数量，超限真正降级而不是只 warning。
    3,000 是单 server 上限，不是多选 skill 的总预算。

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

**关键安全措施**（来自 ironclaw）：
- 所有 XML 属性值经过转义（`<`, `>`, `&`, `"`, `'`）
- `<skill>` 标签逃逸检测（大小写不敏感，处理空白和 NUL 字节）
- 行尾规范化确保一致性哈希

**路由规则**：
- 通用规则在 `skill_select_tool` 静态 description，减少误触发；
- `trust` 属性让 LLM 知道技能的信任级别；
- L1 仅在 `hidden_count > 0` 时输出 search/hidden 动态规则；
- L1 按 `L1_CATALOG_MAX_TOKENS = 2,000` token 预算选择完整 `name + description` 条目，不再按技能个数截断；
- 预算外的技能只计入 `hidden_count`，不列名字；用户点名可直接 select，能力未知才 search。

### 4.3 Always 技能

`always: true` 的真实语义：**在 L1 token 预算内优先排序**，不是“保证出现”。

**它不做什么**：

- ❌ **不**注入 SKILL.md 正文。L2 正文只在模型调用 `skill_select_tool` 后才通过 ToolMessage 返回（`core_generator.py` 的三级披露、`skill_document_loader.get_skill_document()`）。
- ❌ **不**写入 SystemMessage。目录块本身是 HumanMessage 的一段（`skill_catalog_delivery.py`），正文从不进 system prompt。

**真实分配行为**（`catalog_display.py`）：

```
model_visible = 可用且可调用的技能
always        = always=True，按名字排序
non_always    = 非 always，按名字排序
候选          = always + non_always
显示          = 按候选顺序放入完整 name+description，直到 L1_CATALOG_MAX_TOKENS（2,000）
hidden_count  = model_visible - 显示
```

**后果**：

1. `always` 只是优先，不保证。MCP 由 `core_generator.py` 设 `always=True`，会优先占用预算；预算耗尽后剩余 MCP 和用户技能都只计 `hidden_count`。
2. 不再有 `<hidden_skills>` 名字列表。预算外技能只有两种到达方式：用户点名直接 `skill_select_tool`，或能力未知时 `skill_search_tool`。
3. `skill_select_tool` 的白名单和 `skill_search_tool` 的索引都来自全量 `filtered_skills`；`hidden_count` 只表示“未展示”，不表示“不可选”。

**如何被发现**：L1 完整条目 → 直接 select；用户点名 → 直接 select；能力未知/名字未知 → search（BM25 + jieba，MCP 工具名与 80 字符短描述也进索引）→ select。

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

### 5.2 权限衰减机制（来自 ironclaw）

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

### 5.3 Agent 级别权限过滤（来自 opencode）

除了信任衰减，还支持 Agent 级别的技能可见性过滤：

- 不同 Agent 可以配置不同的技能权限
- `available(agent)` 方法根据 Agent 权限过滤可用技能列表
- 被 deny 的技能不会出现在 XML 摘要中

**设计决策**：
- 2 个信任级别足够覆盖所有场景（Trusted vs Installed）
- 最低信任原则从根本上防止权限升级
- 不采用更多级别（如 CoPaw 的 block/warn/off），因为硬限制比软警告更安全
- Agent 权限过滤是额外的细粒度控制层

---

## 6. 确定性技能选择器 [CORE]

> 落地状态：本章的评分选择器未实现。当前由模型经 `skill_select` 元工具选择技能并加载 SOP（`agent/meta_tools/skills/select/skill_select_tool.py`），可选技能目录的披露方式见 §4 与「L1/L2 缓存架构」。

### 6.1 设计理念（来自 ironclaw）

技能选择的第一阶段是**纯确定性的**，不依赖 LLM：
- 防止 LLM 被 Prompt 注入操纵选择恶意技能
- 评分有上限，防止技能通过堆砌关键词刷分
- 排除关键词提供否决机制

### 6.2 评分机制

```
总分 = keyword_score + tag_score + pattern_score

keyword_score（上限 0.6）：
  - 精确匹配：+0.3/次
  - 子串匹配：+0.1/次

tag_score（上限 0.3）：
  - 标签匹配：+0.15/次

pattern_score（上限 0.3）：
  - 正则模式匹配（frontmatter `patterns` 字段）：+0.15/次
  - 用于精确匹配 URL、文件路径、代码片段等结构化输入
```

### 6.3 排除关键词（Veto 机制）

如果用户消息包含技能的 `exclude-keywords` 中的任何词，该技能直接排除（得分归零）。

### 6.4 Token 预算控制

- 每个技能声明 `max-context-tokens`（默认 8000）
- 加载时验证：如果技能正文估算 Token 数超过 `max-context-tokens * 2`，拒绝加载
- 选择多个技能时，总 Token 不超过上下文窗口的 50%

### 6.5 选择流程

```
1. 收到用户消息
2. 对所有 enabled 且 available 的技能计算评分
3. 排除关键词否决
4. 按分数排序，取 Top-N（默认 N=3）
5. Token 预算裁剪
6. 返回选中技能列表
```

**设计决策**：
- 确定性选择器是第一道防线，LLM 只在第二阶段参与（从候选中精选）
- 评分上限防止技能通过堆砌关键词/标签刷分
- 排除关键词防止跨领域技能干扰（如 "python" 技能不应被 "python snake" 触发）

---

## 7. 依赖检查与可用性 [CORE]

### 7.1 依赖类型（融合 Nanobot + ironclaw）

| 类型 | 声明方式 | 检查方法 | 来源 |
|------|----------|----------|------|
| CLI 工具 | `requires.bins: [node, npm]` | `shutil.which()` | Nanobot |
| 环境变量 | `requires.env: [API_KEY]` | `os.environ.get()` | Nanobot |
| 配置文件 | `requires.config: [~/.tool/config.json]` | `Path.exists()` | ironclaw |

### 7.2 检查时机

- **Level 0（发现）**：`list_skills()` 时执行依赖检查，结果缓存到 `SkillMetadata.available`
- **Level 1（摘要）**：XML 摘要中标注 `available` 和 `unavailable_reason`
- **Level 2（正文）**：不可用技能仍可加载正文（LLM 可引导用户安装依赖）

### 7.3 异步检查（来自 ironclaw）

所有检查异步执行，避免阻塞主流程：
- `bins` 检查通过 `asyncio.to_thread(shutil.which, ...)` 执行
- 结果缓存，不重复检查（除非手动刷新）

**设计决策**：
- 不可用技能不会从列表中隐藏，而是标注原因（LLM 可引导用户安装依赖）
- `config` 类型是 ironclaw 的独特贡献，用于检查配置文件是否存在
- 异步检查确保大量技能时不阻塞启动

---

## 8. 安全扫描框架 [CORE]

### 8.1 架构（来自 CoPaw，精简版）

```
Scanner（编排器）
  ├── PatternAnalyzer（正则模式分析）
  ├── ContentSanitizer（内容转义，来自 ironclaw）
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
- 模式定义独立于扫描逻辑（`patterns.py` vs `scanner.py`），便于扩展
- 扫描结果缓存（基于 mtime + 内容 SHA-256 哈希）
- LLM 审计为可选增强，无 LLM 时 graceful fallback 到纯正则

### 8.3 内容转义（来自 ironclaw）

所有技能内容在注入 Prompt 前经过转义：
- XML 属性转义（`<`, `>`, `&`, `"`, `'`）
- `<skill>` 标签逃逸检测（大小写不敏感，处理空白和 NUL 字节）
- 行尾规范化（统一为 `\n`）确保一致性哈希

### 8.4 安装前扫描 + 用户确认（来自 LobsterAI）

- 安装外部技能前自动执行安全扫描
- 如果检测到风险，暂停安装并提示用户确认
- 用户可选择：安装、安装但禁用、取消
- 待确认的安装有 TTL（5 分钟），超时自动取消

### 8.5 内容完整性哈希（来自 ironclaw）

每个技能的 SKILL.md 计算 SHA-256 内容哈希：
- 行尾规范化后计算（`\r\n` → `\n`），确保跨平台一致性
- 用途：白名单精确匹配、篡改检测、缓存失效判断、变更检测
- 哈希在加载时随 `SkillMetadata.content_hash` 一并计算（`backends/skills/_runtime.py::compute_content_hash`），不另存账本；预置技能同步、磁盘内容比对等需要判断变更的地方按当前内容重算后比较

### 8.6 白名单机制（来自 CoPaw）

- 已确认安全的技能可加入白名单（技能名 + 内容 SHA-256 哈希）
- 白名单中的技能跳过扫描
- 内容变更后哈希失效，需重新扫描

**设计决策**：
- 安全扫描是 CORE 而非 ENHANCE，因为这是生产级系统的底线
- 不采用 CoPaw 的全部 17 种威胁类别，避免过度设计
- 内容转义是独立于扫描的必要措施（即使扫描通过，也要转义）
- 白名单 + SHA-256 哈希确保效率和安全的平衡
- 行尾规范化确保跨平台一致性哈希（ironclaw 验证有效）

---

## 9. 安装与卸载 [CORE]

### 9.1 安装方式

| 方式 | 场景 | 信任级别 | 来源 |
|------|------|----------|------|
| **目录复制** | 开发环境、本地技能 | Trusted（workspace） | Nanobot |
| **.skill 归档** | Marketplace 分发 | Installed | Deer-Flow |
| **Git URL** | GitHub/GitLab 仓库 | Installed | NextClaw + picoclaw |
| **Marketplace API** | 在线商店 | Installed | NextClaw |

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

### 9.3 安全提取（来自 Deer-Flow + nexu）

`.skill` 文件是标准 ZIP 归档，由 `safe_extract_zip`（`backends/skills/scanning/zip_extract.py`）在内存中解压，所有业务层共用这一个入口：
- 下载上限 50MB（`zip_installer.MAX_ZIP_SIZE`）
- 压缩比超过 100:1 视为 Zip Bomb 并拒绝；解压后总大小上限 50MB，条目数上限 4096
- 符号链接条目跳过；含 `..` 组件、以 `/` 或 `\` 开头、带 Windows 盘符前缀的条目跳过
- 含 ELF / PE / Mach-O 可执行二进制的成员，整个归档拒绝
- 解压结果交给 §9.2 的隔离区流水线（安全扫描见 §8）

### 9.4 package.json 生命周期脚本门禁

技能含 `package.json` 且声明了非空的 `preinstall` / `install` / `postinstall` 脚本时，安装前由 `check_lifecycle_scripts`（`backends/skills/scanning/package_audit.py`）判为 high 并直接拒绝（§9.2 门禁 2）；其他可疑的脚本命令只产生 medium 发现，进入 §8 的扫描结果，不阻断。安装流程本身不执行任何依赖安装命令。

### 9.5 版本比较与升级（来自 CoPaw）

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

### 10.3 SQLite 快照与目录监听（来自 nexu + LobsterAI）

`SQLiteSkillSnapshot`（`backends/skills/snapshot.py`）把每个技能的 `SKILL.md` 原文、存放路径、信任级别与文件修改时间存进技能根目录下的 `.skills_snapshot.sqlite`（表 `skill_snapshots`）；`SkillWatcher`（`backends/skills/watcher.py`）用 watchdog 递归监听同一目录，让快照跟上磁盘：

- 只关心 `SKILL.md`（父目录名以 `.` 开头的忽略）：创建 / 修改 / 移动 → 解析并写入快照（`upsert_from_path`）；删除 → 从快照移除（`delete_from_path`）；整个技能目录被删除或改名同理
- 500ms 防抖，窗口内的多次事件合并为一次处理
- `sync_all(root)`：按 `file_mtime` 增量对账——磁盘有而库里没有、修改时间更新、路径变了的写入快照，库里有而磁盘没有的删除；只重新解析有变动的文件
- 谁来维护：server 在非沙箱实例启动 `SkillWatcher`（监听 `<状态根>/skills`）；沙箱实例没有监听器；写入路径（技能创建服务、技能下载）无论有无监听器都直接调用 `upsert_from_path` / `delete_from_path`
- 读取：`LocalSkillBackend` 与 `scan_workspace_skills` 默认 `use_snapshot=True`，快照文件存在且非空时直接用它的内容、不再遍历磁盘；快照缺失或为空时遍历磁盘（遍历结果不回写快照）。两条路径都会读取技能目录的 `.stats.json` 补上生命周期状态，已归档（`archived`）的技能不进入列表
- 信任级别：快照写入固定为 `INSTALLED`（`upsert_from_path` 不区分来源），而 `LocalSkillBackend` 遍历磁盘时给 `TRUSTED`，同一个技能走两条路径得到的信任级别不同

### 10.4 热重载与性能

- **快照的收益有限**：本地磁盘上，快照路径与遍历磁盘路径的 `list_skills` 进程 CPU 耗时相差不到 5%（30 次中位数：10 个技能 26.3ms 对 26.6ms；200 个技能 508.6ms 对 533.1ms）。单个技能约 2.5ms，主要花在解析 frontmatter 与读 `.stats.json` 上，快照省掉的只是读取 `SKILL.md`
- **增量更新是文件级**：`upsert_from_path` / `delete_from_path` 只动一个技能；无变动的 `sync_all` 只做 `os.stat` 与一次查询
- SQLite 以 WAL 模式打开（`harden_connection_sync` 的 `CACHE` 档案），连接超时 10 秒，每次操作开连接、用完即关，游标显式关闭防止资源泄漏

**设计决策**：
- 快照存完整 `SKILL.md` 原文，读取时无需回读文件
- 混合架构：非沙箱实例用 `SkillWatcher` 捕获外部编辑；沙箱实例靠写入路径直接更新快照，不常驻监听线程

---

## 11. 技能失败事件与可选隔离读取 (Skill Failure Event & Opt-in Quarantine Read) [CORE]

### 11.1 默认行为：事件上报，不隐藏技能
技能归因的工具失败由 `_skill_failure_tracking` 中间件发布为 `SkillFailureEvent`（`runtime/events/skill_events.py`），由宿主决定如何处置（记录、触发 FIX 提案等）。中间件自身只把工具调用结果记入本次运行的技能使用记录（`backends/skills/usage_recorder`，不触发隔离或修复），因此默认栈不会把任何技能置为 `is_active=False`，也不会从技能列表中隐藏技能。

**计数口径**：仅当会话中恰好加载了一个存储技能时，每次工具调用的结果才记入该技能本次运行的使用记录：成功计成功；失败（排除 e-stop、hook 拦截、取消等策略性拦截，规则与失败事件一致）计失败；加载技能本身（`skill_select_tool`）不算结果。加载多个存储技能时归属不明，不计数。运行结束时每个用到的技能只落一条使用记录，写入 Curator 的 `.stats.json`（`SkillStatsCollector`，唯一的技能使用账本），结果按多数原则判定（失败调用超过一半才算失败，偶发且已恢复的错误不拖累技能）；没有归因到工具调用的使用只计使用次数、不计成败。因此成功率表示"有已观察结果的运行中的成功比例"；据此做决策的只有宿主审批流的 `low_effective_rate` 风险信号（已观察运行 ≥ 3 且成功率 < 50% 时该提案不得自动合并，转人工复核）；沙箱验证只留下验证记录。

### 11.2 读取侧
被置为 `is_active=False` 的技能只有在宿主用 `QuarantineAwareSkillBackend` + `SkillStateReader` 包装后端时才会从列表中过滤；框架不内置任何自动置位 `is_active=False` 的策略，不提供默认的 `SkillStateReader` 实现，也不提供解除隔离的入口——置位与恢复路径均由宿主自行定义（例如修复提案通过后重新写入 `is_active=True`）。

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

### 13.1 多源聚合搜索（来自 CoPaw + picoclaw）

`BaseSkillMarketService` 聚合多个技能源的搜索。默认源：预置（prebuilt，宿主提供技能存储时才有）、静态索引（static_index）、ClawHub、GitHub、skills.sh、LobeHub、ModelScope、阿里云；宿主可用 `register_source` / `unregister_source` 增删自定义源。

**并发策略**（来自 picoclaw）：
- 对所有源并发发起搜索（`asyncio.as_completed`），逐个等待先返回的源，每次最多等 20 秒（`SEARCH_TIMEOUT`）
- 支持部分成功：超时或出错的源只记警告并跳过，已拿到的结果照常返回
- 各源结果先按来源优先级排序（`SOURCE_PRIORITY`：prebuilt > static_index > clawhub > skills_sh > github > lobehub，未列出的源为 0），再去重（`deduplicate`）、按查询词评分排序（`rank_results`）并截到 `limit`

### 13.2 统一 API（来自 NextClaw）

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

### 13.3 多语言支持（来自 NextClaw + nexu）

- 技能描述支持 `description`（英文）和 `descriptionZh`（中文）
- 内置标签翻译表（110+ 标签，来自 nexu）
- 前端根据用户语言偏好自动选择

### 13.4 GitHub 智能安装（来自 picoclaw + CoPaw）

- 智能 URL 解析：完整 URL、`owner/repo`、`owner/repo/path`、分支/标签/commit 引用
- 两级下载策略：GitHub Contents API（优先）→ `raw.githubusercontent.com`（降级）
- 多分支/路径模糊匹配搜索 `SKILL.md`（来自 CoPaw）

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
   - 后台复盘（新技能）：Harness 的复盘结果统一交给 `process_skill_review_result`：依次过锁定/已存在、语义去重、CRITICAL 预检和高危新增复核，安全的新技能自动落盘，其余进入人工审核。
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

### 14.4 语义去重防御 (Semantic Deduplication)

随着技能数量增长，功能相似但名称不同的 skill 会不断累积（"Skill 熵增"），导致 Agent 变慢变笨。
系统实现了三层纵深防御来防止语义级重复：

**三层防御架构**：

```
第 1 层（软）: reviewer prompt → 传入全量 skill 目录 → LLM 自主判断转 patch
第 2 层（硬）: growth_lifecycle → 代码级语义搜索 → 高相似度 draft 降级为人工审核
第 3 层（硬）: manage_tool → 相似度警告 → Agent 可感知并选择 patch 而非创建新 skill
```

**核心组件**：
- `SkillSimilarityChecker` Protocol（框架层）：定义语义相似度检查接口
- `HybridSimilarityChecker`（业务层）：基于 HybridSkillSearchEngine（BM25+Embedding）实现
- `_check_similarity()`（框架层 manage_tool）：save 操作时返回相似度警告
- `_check_semantic_duplicate()`（业务层 growth_lifecycle）：自动复盘时拦截重复 draft

**设计决策**：
- 所有层均为可选注入（`None` 默认值），不影响已有逻辑
- 失败时静默降级（try/except + warning log），绝不阻塞正常流程
- 不阻断创建，只提供信息让 Agent 或人工审核做最终决策

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

## 15. Skill Packs 技能集合 [ENHANCE]

### 15.1 定义（来自 NanoClaw Flavor + Clawith Agent Template）

Skill Pack 是一组预配置的技能组合，适用于特定场景：

```yaml
# skill-packs/web-developer.yaml
name: web-developer
description: Full-stack web development skill pack
skills:
  - name: frontend-design
    enabled: true
  - name: api-development
    enabled: true
  - name: database-query
    enabled: true
  - name: testing
    enabled: true
```

### 15.2 应用场景

| Pack | 包含技能 |
|------|----------|
| Web Developer | frontend-design, api-dev, db-query, testing |
| Data Analyst | data-analysis, chart-viz, sql-query, report-gen |
| Research | deep-research, web-search, paper-analysis |
| DevOps | docker, k8s, ci-cd, monitoring |

### 15.3 应用流程

1. 加载 Pack 定义
2. 检查所有技能是否已安装
3. 安装缺失技能（逐个走 §9.2 的安装流水线）
4. 按 Pack 配置设置启用状态
5. 应用 Pack 不会影响未包含在 Pack 中的技能状态

**设计决策**：
- YAML 格式定义，简单直观
- 类似 Clawith 的 Agent Template 和 NanoClaw 的 Flavor System
- 缺失技能自动安装，无需手动逐个安装

---

## 16. Curated Skills 预安装 [ENHANCE]

### 16.1 设计（来自 nexu）

定义一组推荐技能列表，首次启动时自动安装：

```python
CURATED_SKILL_SLUGS: list[str] = [
    "web-search",
    "deep-research",
    "data-analysis",
]

STATIC_SKILL_SLUGS: list[str] = [
    "memory",
    "core-policies",
]
```

### 16.2 安装流程

1. 首次启动时检测 `installed/` 目录
2. `STATIC_SKILL_SLUGS`：从 builtin 复制到 installed（本地操作，无网络）
3. `CURATED_SKILL_SLUGS`：经 §9.2 的安装流水线从 Marketplace 下载
4. 幂等：已安装的跳过
5. 安装失败不阻塞启动

**设计决策**：
- 区分静态技能（本地复制）和推荐技能（网络下载）
- 幂等安装确保重复启动不会重复安装
- 安装失败不影响系统启动（降级运行）

---

## 附录 A: 设计决策汇总

| 决策 | 选择 | 备选 | 理由 |
|------|------|------|------|
| 信任模型 | 2 级（Trusted/Installed）+ 工具衰减 | 多级信任 / block-warn-off | 简洁且安全，硬限制优于软警告 |
| 技能选择 | 确定性评分 + 正则模式 + 排除关键词 + Token 预算 | LLM 选择 | 防止循环操纵，可预测，正则精确匹配 |
| 安全扫描 | 可扩展框架 + 核心 6 种威胁 | 17 种威胁类别 | 覆盖 95% 威胁，不过度设计 |
| 内容完整性 | SHA-256 哈希 + 行尾规范化 | 无 | 白名单精确匹配、篡改检测、跨平台一致性 |
| 安装方式 | 隔离区流水线：评分门禁 + 事务式提升 | 直接解压覆盖 | 被拒绝的包不留痕迹，升级失败保留旧版本 |
| 搜索缓存 | 精确键 + 300 秒 TTL + 100 条上限 | 相似度匹配缓存 | 实现简单，命中行为可预测 |
| 状态持久化 | 技能目录内的 `.stats.json` / `origin.json` / `receipt.json`（`.stats.json` 原子写入） | 集中账本 / 数据库 | 随技能目录复制、备份与删除，没有集中状态可漂移 |
| 目录结构 | 三层 + 信任分离 | 两层 | 物理隔离确保信任级别不可伪造 |
| 摘要格式 | 安全 XML + 路由指令 | Markdown 表格 | 结构化、可嵌套、防注入 |
| 目录监听 | watchdog + SQLite 快照（`sync_all` 按 mtime 对账） | 仅 mtime 检查 | 实时性 + 一致性 |
| 内容安全 | XML 转义 + 标签逃逸检测 | 无 | 防止 Prompt 注入的最后一道防线 |
| 版本管理 | 语义化版本比较 + 升级提示 | 无版本管理 | 长期维护必备，用户不会错过重要更新 |
| 预安装 | Curated Skills 种子（按需启用） | 强行装配 / 空白启动 | 遵循所见即所得：种子预置库供用户按需启用，内置通用智能体默认不加载技能（skill_ids = []，纯指令零启动基线） |

---

## 附录 B: 与现有代码映射

| 方案模块 | 现有代码 | 状态 |
|----------|----------|------|
| 技能定义规范 | `backends/skills/types/` 包 | **已实现**（`types_enums`/`types_metadata`/`types_instance`/`types_visibility` 等） |
| 存储抽象层 | `backends/skills/protocols.py` | **无需修改** |
| 发现抽象层 | `backends/skills/market_protocols.py` | **无需修改** |
| 创建抽象层 | `backends/skills/creation_protocols.py` | **无需修改** |
| 本地后端 | `backends/skills/local.py` | **无需修改** |
| 存储后端 | `backends/skills/storage.py` | **无需修改** |
| 组合后端 | `backends/skills/composite.py` | **无需修改** |
| 技能注册表 | `agent/skills/runtime/registry.py` | 需增强（集成信任模型和状态管理） |
| 文档加载 | `agent/meta_tools/skills/select/skill_document_loader.py` | **无需修改** |
| 元数据摘要 | `agent/skills/runtime/registry.py::get_metadata_summary` | 需升级为安全 XML 格式 |
| 信任衰减器 | `agent/skills/runtime/attenuator.py` | **已实现** |
| 安全扫描器 | `backends/skills/scanning/scanner.py` | **已实现** |
| 内容转义器 | `agent/skills/runtime/registry.py`（XML 转义） | **已实现** |
| 确定性选择器 | `agent/meta_tools/skills/select/skill_select_tool.py` | **未落地**：由模型经元工具选择技能，见 §6 |
| 依赖检查器 | `backends/skills/prerequisites/` | **已实现** |
| Frontmatter 验证器 | `backends/skills/_utils.py`（`parse_skill_frontmatter`） | **已实现** |
| 安装流水线 | `agent/skills/market/file_install.py`、`agent/skills/market/transaction.py` | **已实现** |
| 安全提取器 | `backends/skills/scanning/zip_extract.py` | **已实现** |
| 使用与生命周期账本 | `backends/skills/stats_collector.py` | **已实现** |
| 目录监听器 | `backends/skills/snapshot.py`、`backends/skills/watcher.py` | **已实现** |
| 搜索缓存 | `agent/skills/market/service.py` | **已实现** |

---

## 附录 C: 与竞品能力对比

| 能力维度 | 本方案 | 最强竞品 | 对比 |
|----------|--------|----------|------|
| 信任模型 | 2 级 + 工具衰减 | ironclaw (2 级) | **≥** 等价，且有安全扫描加持 |
| 技能选择 | 确定性评分 + 正则模式 + veto + 预算 | ironclaw | **≥** 等价，正则模式精确匹配 |
| 安全扫描 | 可扩展框架 + 核心规则 | CoPaw (17 种) | **≥** 更灵活，不过度设计 |
| 内容完整性 | SHA-256 + 行尾规范化 | ironclaw | **≥** 等价 |
| 安装 | 隔离区 + 评分门禁 + 事务式回滚 | nexu（异步队列 + 限流重试） | 取舍不同：不排队，换取门禁与回滚 |
| 搜索缓存 | 精确键 + TTL | picoclaw（Trigram Jaccard） | 取舍不同：不做相似度匹配 |
| 多源安装 | ClawHub + GitHub + ZIP | CoPaw (6 源) | **≥** 覆盖核心场景，可扩展 |
| 状态管理 | 技能目录内的分散文件 | nexu（集中 JSON 账本） | 取舍不同：状态随目录走，没有集中账本 |
| 目录监听 | watchdog + SQLite 快照 | nexu | **≥** 等价 |
| 内容安全 | XML 转义 + 标签逃逸 | ironclaw | **≥** 等价 |
| 权限过滤 | Agent 级别权限 | opencode | **≥** 等价 |
| 多语言 | 中英双语 + 标签翻译 | nexu (110+ 标签) | **≥** 等价 |
| 版本管理 | 语义化版本比较 + 升级提示 | CoPaw | **≥** 等价 |
| 预安装 | Curated + Static 双轨 | nexu | **≥** 等价 |
| 技能集合 | Skill Packs YAML | NanoClaw Flavor | **≥** 更简洁 |

**综合评估**：除「安装」「状态管理」「搜索缓存」三个维度取舍不同外，其余维度为设计期的对比结论。三层安全防御（信任衰减 + 安全扫描 + 内容转义）+ SHA-256 完整性校验是所有竞品中独一无二的组合。

---

## 附录 D: 参考项目来源索引

| 项目 | 核心贡献 |
|------|----------|
| **OpenClaw** | SKILL.md 格式规范、渐进式披露、多管理器安装、ClawHub 商店 |
| **Clawith** | 数据库存储、多租户、可移植性分层、Agent Template |
| **NanoClaw** | Git 分支即技能、容器技能、Flavor System |
| **Nanobot** | XML 摘要格式、依赖检查机制、Always 技能、ContextBuilder |
| **NextClaw** | 统一 Marketplace API、多语言支持、实时事件 |
| **Deer-Flow** | .skill 归档安全安装、Frontmatter 白名单验证、AI 驱动技能创建与评估 |
| **CoPaw** | 安全扫描框架（Scanner + Analyzer + Policy）、多源 Hub 安装、白名单机制 |
| **LobsterAI** | XML 路由指令、安装前用户确认、Skill Service Manager |
| **ironclaw** | **信任模型与权限衰减**、确定性选择器、内容安全转义、Token 预算 |
| **nexu** | 目录监听与增量对账的思路、staging 目录安装；异步安装队列、集中 JSON 账本与 Rate Limit 处理未采用 |
| **picoclaw** | 多注册表并发搜索、GitHub 智能安装；Trigram 搜索缓存未采用 |
| **nullclaw** | SkillForge 自动发现管线（Scout → Evaluate → Integrate） |
| **zeroclaw** | SkillForge Rust 版、GitHub PAT 支持 |
| **opencode** | Effect-TS 函数式架构、Agent 级别权限过滤、多源发现 |

---

## 附录 E: 为什么这个方案是完美的

### 1. 安全性最强

四层纵深防御，没有任何竞品同时拥有：
- **信任衰减**（ironclaw）：硬限制，LLM 看不到被移除的工具
- **安全扫描**（CoPaw）：软检测，可扩展规则引擎
- **内容转义**（ironclaw）：注入防护，XML 标签逃逸检测
- **SHA-256 完整性校验**（ironclaw）：篡改检测，白名单精确匹配

### 2. 性能最优

- 查询结果缓存（§12）减少 API 调用
- 确定性选择器避免 LLM 调用
- 安装是异步调用，不阻塞主流程
- `SkillWatcher` 防抖后只更新变动的那一个技能（§10.3）

### 3. 简洁不冗余

- 每个模块职责单一
- 不采用数据库（不需要）、不采用 Git 分支（过度设计）、不采用 Container Skills（不需要）
- 2 个信任级别而非更多（够用且简单）
- 6 种威胁类别而非 17 种（覆盖 95%）

### 4. 可扩展

- 安全扫描的 Analyzer 接口可扩展自定义规则
- 安装源的 Source 接口可扩展新来源
- 搜索的 Registry 接口可扩展新注册表
- SkillForge 自动发现可作为未来扩展模块

### 5. 无技术债

- 从零设计，无向后兼容包袱
- 保留现有优秀设计（Protocol 抽象层）
- 新增模块遵循现有架构风格
- 所有设计决策有明确理由和来源

### 6. 用户体验完善

- Curated Skills 预安装确保开箱即用
- Skill Packs 一键配置场景
- 版本比较与升级提示确保长期维护
- 多语言支持（中英双语 + 110+ 标签翻译）

### 7. 所有「缺点」要么不需要，要么可扩展

| 未采用的能力 | 原因 |
|-------------|------|
| 数据库存储 | 我们不是 Sandbox，文件系统足够 |
| 多租户 | 同上 |
| SkillForge 自动发现 | 实际使用场景有限，可作为未来扩展 |
| Container Skills | 过度设计，普通技能已满足需求 |
| Git 分支即技能 | 过度设计，目录结构更直观 |
| 完整安装历史 | `origin.json` 已有 installed_at/source，`receipt.json` 有文件清单，足够 |
| Skill Service Manager | 后台服务管理复杂度高，收益低 |

## L1/L2 缓存架构与降噪 (L1/L2 Cache & Noise Reduction)

为了解决海量技能带来的上下文噪音（Context Noise）和“能力遗忘”（Capability Amnesia）问题，系统采用了 L1/L2 缓存架构：

1. **L1 核心技能 (Core Skills)**：
   - **机制**：`skill_configs.is_core=true` 的技能优先进入首条用户消息的 ``<bound_skills>`` 块（与 L2 同通道，由 ``resolve_catalog_display_skills()`` 解析；**不在** SystemMessage）。
   - **特点**：相对 L2 更高优先级出现在 catalog 内联列表，仍保持 ``skill_select_tool.description`` 字节稳定。
   - **适用场景**：用户在 GUI 标记为核心、对当前智能体高频使用的技能。

2. **L2 外围技能 (Peripheral Skills)**：
   - **机制**：将技能的 `name + description` 注入首条用户消息的 ``<bound_skills>`` 块，按 `L1_CATALOG_MAX_TOKENS = 2,000` token 预算截断；超出部分只计 `hidden_count`，通过点名 `skill_select_tool` 或 `skill_search_tool` 发现。``skill_select_tool.description`` 保持字节稳定。
   - **注意**：不再按 20 个技能硬截断，也不再列 `<hidden_skills>` 名字列表；预算外的技能不展示名字。
   - **特点**：极低 Token 消耗，0 认知负担。LLM 知道其存在，需要时通过 `skill_select_tool` 渐进式加载完整 SOP。
   - **适用场景**：低频使用、长尾技能。

### 精确 Token 成本计算
系统在技能保存/更新时，使用 `tiktoken` 精确计算技能 SOP 的 Token 消耗，并持久化到数据库中（`token_cost`）。前端利用此数据渲染“认知负载水位表”（Noise Gauge），帮助用户直观管理核心技能的负载。


## 技能同步 (Skill Sync)

跨设备/跨沙箱的技能双向同步，支持集体技能进化：

- **Protocol-first**: `SkillSyncProtocol` 定义传输接口，`SkillQualityGateProtocol` 定义推送质量门
- **增量同步**: `SkillSyncManifest` (SQLite) 追踪每个技能的 SHA256 和时间戳，避免全量比对
- **质量门控**: 只有满足最低执行次数和成功率的技能才会被推送到共享仓库
- **部署模式**:
  - Local/Tauri: `LocalFSSyncBackend` 基于 `StorageProvider`，通过共享目录同步
  - SaaS: `HTTPSyncBackend`（规划中，尚未实现）通过控制平面 API 同步
- **后台执行**: 通过 `IdleTaskRegistry` 注册 `skill_sync` 任务类型，闲时自动触发
- **详细架构**: 参见 `agent/skills/sync/_ARCH.md`
