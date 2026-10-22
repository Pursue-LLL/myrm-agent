# components/features/artifacts/factcheck 模块架构

## 架构概述

虚构占位高亮交互横幅、待核验清单抽屉与事实核查溯源侧边栏套件。对标腾讯 WorkBuddy 核心人机交互设计“不编造但把虚构管起来”，彻底打破传统 AI 生成文章时读者无法分辨“哪些是真实发生、哪些是模型即兴演练”的黑盒界面，为交付物提供工业级严谨度保障。

核心能力：
1. **正文虚构占位高亮与徽章 (`FabricationPlaceholderBadge.tsx`)**：自动识别 `[待替换占位: xxx]` 与 `{{placeholder:xxx}}`，渲染高反差浅黄色警示徽章，点击可直接聚焦右侧抽屉；
2. **顶部诚实守卫与待核验交互横幅 (`HonestyAuditBanner.tsx`)**：在正文顶部显式告警未实测占位数量，支持一键打开抽屉与一键定稿；
3. **右侧事实核查与占位管理抽屉 (`FactCheckSheetDrawer.tsx`)**：双 Tab 视图，Tab 1 就地回填真实跑测数据并一键替换正文，Tab 2 展示经权威实测或联网检索核实的硬事实清单与信源链接；
4. **事实核查引擎服务 (`factCheckService.ts`)**：实现正则提取、上下文切片抓取、单项替换与批量替换定稿。

## 文件清单

| 文件 | 地位 | 职责 | I/O/P |
|------|------|------|-------|
| `factCheckTypes.ts` | 核心 | 占位项、核验事实与审计报告强类型 DTO 契约 | ✅ |
| `factCheckService.ts` | 核心 | 占位解析、上下文摘要截取、单项/批量替换算法与报告编译 | ✅ |
| `FabricationPlaceholderBadge.tsx` | 组件 | 正文内嵌浅黄色虚构占位徽章与点击联动 | ✅ |
| `HonestyAuditBanner.tsx` | 组件 | 顶部诚实守卫交互横幅（占位警示、抽屉唤起与定稿状态指示） | ✅ |
| `FactCheckSheetDrawer.tsx` | 组件 | 右侧双 Tab 抽屉（待替换占位填报工作台 + 已核实事实追溯清单） | ✅ |
| `index.ts` | 门面 | 统一导出公共组件与服务类型 | ✅ |

## 设计原则

- **把虚构管起来**：不阻止模型排版时的即兴演练，但必须将未实测数字以结构化方式暴露给用户进行真实核验。
- **纯矢量与零 Any**：全量使用 Lucide SVG 矢量图标，严禁原生 emoji 与 `any` 类型。
