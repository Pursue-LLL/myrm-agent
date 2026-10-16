# core/skills/creation 模块架构


---

## 架构概述

技能创建服务。提供 Skill 创建的业务逻辑层，包括验证、持久化和初始化。

当前实现要点：
- 保存前统一走 `parse_skill_frontmatter()`，与 runtime 加载使用同一套严格 frontmatter 解析规则
- `contract` 等结构化字段在创建阶段即被校验，避免坏技能先写入、后加载失败
- 描述优先取 frontmatter 中的 `description`，不再依赖浅解析兜底
- 写入资源时执行静态语法校验（`.py` 走 `ast.parse`，`.json` 走 `json.loads`，`.yaml`/`.yml` 走 `yaml.safe_load`），拦截语法错误的资源落盘
- 新建技能时自动注入 `evolution-locked: true` 到 frontmatter，保护用户技能免受 Curator 自动化误操作
- `skill_manage` 的撤销快照读自写入根（`ManagedSkillSnapshotReader`），不经一轮对话的技能后端：后者只列出本轮挂载的技能，据其拍的快照会把已有技能记成「批次前不存在」，撤销时整个技能被删

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `managed_skill_reader.py` | ✅ 核心 | `ManagedSkillSnapshotReader` — 直接读 `skill_creation_service.base_path` 下技能的 `SKILL.md` 与资源（路径经 `safe_join_path` 防越界，每次调用读取当前根，缺失即抛 `FileNotFoundError`），作为 `skill_manage` 批次改动前快照的来源；由 `tool_setup._setup_skill_manage_tool` 注入 |
| `service.py` | ✅ 核心 | `SkillCreationService` — 技能创建服务（默认写入 `models.LOCAL_SKILLS_DIR`，即目录扫描主根）；保存前执行严格 frontmatter/contract 校验，资源写入执行 Python AST、JSON、YAML 语法校验，`skill_creation_service` 全局实例 |
