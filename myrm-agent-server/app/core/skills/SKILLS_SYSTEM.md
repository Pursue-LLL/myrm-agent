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
    → 老用户：增量启用新种子（尊重 disabled_prebuilt_ids）
builtin_initializer                  BuiltIn Agent 预绑定 default_skill_ids（is_core=false）
```

存储路径约定见 `myrm_agent_harness.toolkits.storage.paths`（`SKILL_METADATA_FILE = _metadata.json`）。

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
