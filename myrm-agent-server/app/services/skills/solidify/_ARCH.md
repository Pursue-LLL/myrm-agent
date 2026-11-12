# services/skills/solidify 模块架构

## 架构概述

本子包把一份交付物（如 HTML 课件、可视化图表、数据看板）渲染成四文件资产包，并为它登记一个干净的预览页；资产包与预览页只保存在进程内存，不写入技能库。

核心包含三项能力：
1. **参数槽位提取**：优先取内容里显式的 `{{name}}` 槽位；没有时，对 HTML 取 `<title>` 作为 `topic`，没有 `<title>` 才取 `<h1>` 作为 `headline`；仍然没有则给出默认的 `topic` 槽位；
2. **四文件资产包渲染**：生成 `SKILL.md`（YAML frontmatter + 使用说明）、`assets/example.html`、`assets/template.html`（把槽位默认值替换为占位符）与 `references/design_guidelines.md`；
3. **干净预览页**：登记交付物内容并由 `GET /preview/{preview_id}` 提供，响应头放宽 CSP 并带 `Referrer-Policy: no-referrer`，使内嵌资源在完整浏览器标签页里正常加载。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `solidify_types.py` | 核心 | 固化请求、参数规则、资产包、固化结果与预览请求/元数据 Pydantic 契约 | ✅ |
| `skill_solidify_service.py` | 核心 | 单例服务：参数槽位提取、资产包渲染、预览页登记与读取，资产包与预览页保存在进程内注册表 | ✅ |
| `__init__.py` | 门面 | 导出公共类型与服务 | ✅ |

## 约束

- **进程内状态**：`_skills_registry` 与预览缓存只存在于当前进程，重启后清空；资产包只能经 `SkillSolidifyService.get_skill_bundle` 读取，没有对应的 HTTP 端点。
- **预览页放宽 CSP**：预览页响应头为 `default-src * 'unsafe-inline' 'unsafe-eval' data: blob:`，登记进来的内容（`POST /preview` 接受任意内容）可以运行脚本并加载任意来源的资源。
