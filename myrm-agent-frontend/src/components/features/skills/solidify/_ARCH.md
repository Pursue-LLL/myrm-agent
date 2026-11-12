# components/features/skills/solidify 模块架构

## 架构概述

交付物固化向导组件包：调用服务端固化接口，展示参数槽位与四文件资产清单；资产包只保存在服务端进程内存，不写入技能库。该向导目前没有被任何页面引用。

核心机制：
1. **参数最小化自动提取**：仅提取必须变动的动态入参槽位（如 `{{topic}}`, `{{headline}}`），固定骨架、样式与动画；
2. **四位一体全包生成向导**：生成 `SKILL.md` + `assets/example.html` + `assets/template.html` + `references/design_guidelines.md`；
3. **外部浏览器预览入口**：固化结果里带预览地址，可在系统浏览器中打开，校验渲染表现。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `solidifyTypes.ts` | 核心 | 参数规则、固化请求与四位一体资产包前端 DTO 契约 | ✅ |
| `solidifyService.ts` | 核心 | 客户端启发式参数提取与服务端固化 API 调用 | ✅ |
| `SolidifyStepParams.tsx` | 核心 | 步骤一：参数最小化提取视图（基本信息与动态插值槽位配置） | ✅ |
| `SolidifyStepBundle.tsx` | 核心 | 步骤二：四位一体资产包预览视图（目录结构与规划门禁开关） | ✅ |
| `SolidifyToSkillWizardModal.tsx` | 核心 | 向导交互模态框（流程编排、结果展示与外部浏览器预览入口） | ✅ |
| `index.ts` | 门面 | 统一导出公共组件与类型定义 | ✅ |

## 设计原则

- **参数最小化原则**：杜绝盲目全量泛化，只将必须变动的要素作为参数暴露，确保生成的高确定性。
- **全包四位一体**：资产包固定包含 `SKILL.md`、示例、模板与设计规范四个文件，不只生成孤立的 prompt。
- **接口失败的回落**：固化接口请求失败时，向导用本地构造的成功结果（预览地址 `/api/v1/skills/solidify/preview/local-mock`）继续走到完成页，不显示接口错误。
- **零原生 emoji**：全量使用 Lucide SVG 矢量图标。
