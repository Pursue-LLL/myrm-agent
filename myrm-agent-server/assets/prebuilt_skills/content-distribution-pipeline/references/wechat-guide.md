# WeChat Official Account (微信公众号) Distribution Guide

## Platform Characteristics & Reader Psychology

WeChat Official Account readers favor **in-depth narrative, structured thought leadership, authoritative benchmarks, and clean visual typography**.

- **Core Goal**: Build authority, convey complex logic, and provide shareable reference materials.
- **Tone**: Professional, analytical, insightful, and structured with clear hierarchy.

---

## Deliverable Standard

Every WeChat Official Account adaptation task MUST produce:

1. **Structured Article Markdown (`wechat/article.md`)**: Complete long-form article formatted for WeChat rendering.
2. **WeChat Styled HTML (`wechat/article.wechat.html`)**: Compiled HTML with inline CSS via `wechat-article-formatter`.
3. **Banner & Cover Specs (`wechat/visual_specs.md`)**:
   - Primary Header Banner: 2.35:1 aspect ratio (900 × 383 px).
   - Thumbnail Icon: 1:1 aspect ratio (square).

---

## Content Structure & Narrative Architecture

```markdown
# [Authoritative & Insightful Title]

> 导读 / 核心摘要：[100-150字，点明核心价值、行业痛点及本文给出的完整解决方案]

## 01 背景与痛点：为什么传统方式正在失效？
- [行业现状与真实挑战]
- [传统解决方案的瓶颈与边界]

## 02 核心解法：新架构/新范式是如何工作的？
- [架构图/核心逻辑拆解]
- [关键机制与技术亮点（代码/数据/逻辑）]

## 03 实战对比与实测收益
- [A vs B 真实数据对比表格]
- [落地效果与可复现指标]

## 04 适用边界与避坑指南
- [什么场景适合 / 什么场景不适合]
- [落地时的注意事项]

## 05 结语与行动建议
- [总结展望与一句话沉淀]
```

---

## HTML Formatting & Styling Rules

- **Headings & Blockquotes**: Emphasize key quotes with subtle left borders and soft background cards.
- **Code Highlighting**: Syntax highlighted using Pygments inline style tokens.
- **Mobile First**: All tables and code blocks must support horizontal scrolling without breaking the layout width.
- **Draft Push Workflow**: Ensure the user can preview the compiled `.wechat.html` artifact in WebUI and push to WeChat draft with one click.
