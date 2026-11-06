# backends/skills/_utils/

## 架构概述

SKILL.md frontmatter 与 contract 的解析：字段校验、contract 子结构、入口组装分层，`__init__.py` 是唯一门面。上级：[../_ARCH.md](../_ARCH.md)。

## 文件清单

| 文件 | 职责 |
|------|------|
| `__init__.py` | 聚合导出 parse_skill_frontmatter / SkillFrontmatter 等 |
| `frontmatter.py` | 常量、SkillFrontmatter、YAML 解析与字段校验 |
| `contract.py` | requires / steps / judgments / traps / verifications 解析 |
| `parsing.py` | 解析入口与字段组装 |
