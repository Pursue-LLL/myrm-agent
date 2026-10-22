# components/features/skills/solidify 模块架构

## 架构概述

会话成果一键固化为专属 Skill 向导组件包。对标纳米Work 交互设计与智见 Skills 官方最佳实践（`scholar-stickers` 实操），实现将用户在会话与工件中打磨成熟的复杂成果（如单文件 HTML 课件、大屏图表、数据看板等）一键沉淀为可复用的专属 Skill。

核心机制：
1. **参数最小化自动提取**：仅提取必须变动的动态入参槽位（如 `{{topic}}`, `{{headline}}`），固定骨架、样式与动画；
2. **四位一体全包生成向导**：生成 `SKILL.md` + `assets/example.html` + `assets/template.html` + `references/design_guidelines.md`；
3. **外部浏览器即时检验**：固化后可一键在系统真实浏览器中打开预览，校验渲染表现。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `solidifyTypes.ts` | 核心 | 参数规则、固化请求与四位一体资产包前端 DTO 契约 | ✅ |
| `solidifyService.ts` | 核心 | 客户端启发式参数提取与服务端固化 API 调用 | ✅ |
| `SolidifyStepParams.tsx` | 核心 | 步骤一：参数最小化提取视图（基本信息与动态插值槽位配置） | ✅ |
| `SolidifyStepBundle.tsx` | 核心 | 步骤二：四位一体资产包预览视图（目录结构与规划门禁开关） | ✅ |
| `SolidifyToSkillWizardModal.tsx` | 核心 | 三步向导交互模态框（流程编排、落盘完成与外部真机测试） | ✅ |
| `index.ts` | 门面 | 统一导出公共组件与类型定义 | ✅ |

## 设计原则

- **参数最小化原则**：杜绝盲目全量泛化，只将必须变动的要素作为参数暴露，确保生成的高确定性。
- **全包四位一体**：生成的 Skill 必须包含完整的模板与测试样例资产，不能只生成孤立的 prompt。
- **零原生 emoji**：全量使用 Lucide SVG 矢量图标。
