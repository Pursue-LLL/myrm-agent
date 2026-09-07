# Xiaohongshu (小红书) Distribution Guide

## Platform Characteristics & Algorithm Principles

Xiaohongshu is a decision-making and lifestyle search engine. Users browse with high intent: "Is it worth buying?", "How do I solve this pain point?", "What are the real traps to avoid?".

- **Core Goal**: Drive CTR through high-impact 3:4 cover cards + title, then convert through actionable, structured points.
- **Tone**: Authentic, peer-to-peer, high value-density, formatted with bullet points and clear tags.

---

## Deliverable Standard

Every Xiaohongshu adaptation task MUST produce:

1. **Dual Editions**:
   - **Edition A (`xiaohongshu/pain_point_edition.md`)**: Pain-point decision / Avoid pitfalls (拔草/避坑决策版). Focuses on "who shouldn't buy/use", "common misconceptions", "actual trade-offs".
   - **Edition B (`xiaohongshu/lifestyle_edition.md`)**: Experience review / Grass planting (种草测评/场景实操版). Focuses on "step-by-step workflow", "efficiency leap", "hands-on delight".
2. **Title Pool (`xiaohongshu/titles.json`)**: 5 formulaic candidate titles.
3. **Visual Specs (`xiaohongshu/visual_specs.md`)**: 3:4 ratio cover card layout, color palette, and headline text.

---

## 5-Type High-CTR Title Formulas

Generate at least one candidate for each category in `xiaohongshu/titles.json`:

1. **Contrast / Subversion (反差颠覆型)**:
   - *Formula*: [Common consensus] vs [Shocking reality]
   - *Example*: "以为只是普通升级？用完彻底推翻了我对 AI 工具的认知"
2. **Numerical & Quantified (数字量化型)**:
   - *Formula*: [Specific number] + [Time/Effort reduction] + [Concrete outcome]
   - *Example*: "实测3分钟搞定全平台排版，运营效率提升80%的秘密"
3. **Pitfall / Warning (避坑警示型)**:
   - *Formula*: "先别急着[Action]！[Group]必看的[Topic]避坑指南"
   - *Example*: "先别急着买单！深度测评后告诉你哪些人千万别用"
4. **Targeted Question (人群痛点追问型)**:
   - *Formula*: "[Specific audience]还在为[Specific pain]头疼？看这篇就够了"
   - *Example*: "自媒体主编还在手动改稿？一键多平台分发保姆级教程"
5. **Emotional Resonance (情绪共鸣/自用分享型)**:
   - *Formula*: "谁懂啊！终于找到能[Key benefit]的神仙工具了"
   - *Example*: "谁懂啊！被低效二创折磨半年的我终于解脱了"

---

## Content Structure Template

### Edition A: Pain-point & Decision

```markdown
# [Selected Title]

💡 结论先行：[一句话核心论断，谁适合用 / 谁千万别用]

⚠️ 3大踩坑重灾区：
1. [痛点 1]：[简要说明及传统方案痛点]
2. [痛点 2]：[简要说明]
3. [痛点 3]：[简要说明]

🛠️ 真实解决方案：
- [核心动作 1]：[具体价值]
- [核心动作 2]：[具体价值]

📌 最终决策建议：
- 推荐人群：[用户画像 A、B]
- 劝退人群：[用户画像 C]

#工具推荐 #效率神器 #干货分享 #[领域标签]
```

### Edition B: Experience Review & Workflow

```markdown
# [Selected Title]

🔥 沉浸式体验：[一句话说明实操场景与痛点解决]

✨ 3个惊艳瞬间：
1. 🌟 [亮点 1]：[具体实操体验]
2. ⚡ [亮点 2]：[效率对比与数据]
3. 🎯 [亮点 3]：[细节打动点]

📝 3步上手保姆级流程：
- Step 1: [第一步输入/配置]
- Step 2: [第二步自动化流转]
- Step 3: [第三步一键导出]

💬 真实感受：[一句话中肯总结]

#自媒体运营 #生产力工具 #好物推荐 #[领域标签]
```
