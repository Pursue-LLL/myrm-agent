# services/skills/solidify 模块架构

## 架构概述

本子包负责将用户会话与工件中打磨成型的优质交付物（如 HTML 课件、可视化图表、数据看板等）一键固化为标准全包可复用 Skill，对标纳米Work 与智见 Skills `scholar-stickers` 最佳实践。

核心包含三大能力：
1. **参数最小化自动提取**：分析工件内容，仅将动态变化要素（如 `{{topic}}`, `{{headline}}`）暴露为入参，静态骨架和样式锁死；
2. **四位一体标准资产包生成**：自动生成 `SKILL.md`（YAML frontmatter + 规划指令）+ `assets/example.html` + `assets/template.html` + `references/design_guidelines.md`；
3. **外部浏览器真机预览通道**：提供带 CSP 放行与 `Referrer-Policy: no-referrer` 的隔离预览服务，根除内嵌 iframe 图片裂图与同源沙箱痛点。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `solidify_types.py` | 核心 | 固化请求、动态参数提取规则、四位一体资产包及纯净预览 Pydantic 契约 | ✅ |
| `skill_solidify_service.py` | 核心 | 单例服务：参数最小化提取、资产包渲染编排、预览注册与读取 | ✅ |
| `__init__.py` | 门面 | 导出公共类型与单例服务 | ✅ |

## 设计原则

- **参数最小化原则**：不把整个页面泛化，仅暴露少量动态变动参数，保证生成的确定性与高质量。
- **真机无阻断预览**：预览路由独立托管，避免受宿主前端 iframe CSP/同源策略限制。
