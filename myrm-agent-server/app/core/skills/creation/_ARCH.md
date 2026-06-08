# core/skills/creation 模块架构


---

## 架构概述

技能创建服务。提供 Skill 创建的业务逻辑层，包括验证、持久化和初始化。

当前实现要点：
- 保存前统一走 `parse_skill_frontmatter()`，与 runtime 加载使用同一套严格 frontmatter 解析规则
- `contract` 等结构化字段在创建阶段即被校验，避免坏技能先写入、后加载失败
- 描述优先取 frontmatter 中的 `description`，不再依赖浅解析兜底
- 新建技能时自动注入 `evolution-locked: true` 到 frontmatter，保护用户技能免受 Curator 自动化误操作

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `service.py` | ✅ 核心 | `SkillCreationService` — 技能创建服务；保存前执行严格 frontmatter/contract 校验，`skill_creation_service` 全局实例 |
