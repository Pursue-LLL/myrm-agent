# health/

## 架构概述

System Doctor 健康检查仪表盘与修复引导，含诊断导出能力。健康数据仅在用户打开 Settings → System 或访问 `/health` 时通过 `GET /health/doctor` 按需拉取。

面向用户的行文走本地化：状态、组件标题、一句话处置建议都取自 locale（`settings.systemHealth.doctor.{status,components,hints,errors}`）；后端返回的英文 `message` / `detail` / `measured` / `expected` / `cause` / `fix_suggestion` 与原始组件名只放在默认折叠的「技术详情」里，供排障与反馈使用。

## 文件清单

| 文件                                                    | 地位     | 职责                                                                                                                                                                                  |
| ------------------------------------------------------- | -------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `DoctorDashboard.tsx`                                   | 核心组件 | 系统诊断看板：健康评分、状态过滤、按展示文案搜索、技术详情总开关（`aria-expanded`）、修复卡片、诊断导出                                                                               |
| `doctorReportView.ts`                                   | 视图模型 | 纯函数 `describeReport`：把一条 `HealthReport` 解析为标题 / 一句话建议 / 技术详情行（locale key 或原文）；`DOCTOR_LOCALE_KEYS` 是行视图可引用的全部 locale key 清单                   |
| `DoctorReportRow.tsx`                                   | 子组件   | 单条报告行：状态图标、本地化标题与建议、状态徽标、折叠的技术详情；`DesktopControl` WARN 时展示系统设置深链按钮；导出 `STATUS_TEXT_CLASS`（浅/深色成对的状态文字色）                   |
| `GuidedRepairCard.tsx`                                  | 子组件   | 引导式修复卡片，支持 dry_run 和 confirm                                                                                                                                               |
| `doctor-icons.tsx`                                      | 图标集   | DoctorDashboard 专用 SVG 图标组件集                                                                                                                                                   |
| `__tests__/doctorReportView.test.ts`                    | 测试     | 视图模型：code 译文优先、组件×状态建议、通用建议回退、函数名标题归一为通用标题、技术详情行顺序与空字段省略（vitest）                                                                  |
| `__tests__/doctorLocaleKeys.test.ts`                    | 测试     | 六语言对 `DOCTOR_LOCALE_KEYS` 全部非空，且 locale 的行文案子树不含视图从不引用的 key（vitest）                                                                                        |
| `__tests__/DoctorDashboard.presentation.test.tsx`       | 测试     | 真实 next-intl 渲染（en/zh）：标题/状态/建议本地化、英文原文与函数名默认不可见、技术详情开合、按标题/英文原文/原始组件名搜索、无结果空态（vitest）                                    |
| `__tests__/DoctorDashboard.desktopControlWarn.test.tsx` | 测试     | WARN + `settings_deeplinks` 深链按钮渲染与 click fallback（vitest）                                                                                                                   |
| `__tests__/DoctorDashboard.verdictI18n.test.tsx`        | 测试     | 真实 next-intl：有 locale 文案的 code 显示译文，无 locale 文案的 code 回退到本地化建议且后端 `message` 仅在技术详情内；`ERR_VECTOR_STORE_ON_MEMORY_FALLBACK` 六语言译文非空（vitest） |

## 依赖

- `@/services/runtime-health` — /doctor API 客户端与 `HealthReport` 类型
- `@/lib/desktop/permissionDeepLink` — DesktopControl WARN 深链 pick/open
- `@/lib/utils/diagnostic-export` — 诊断报告格式化与导出（Markdown/JSON，Markdown 含 measured/expected/cause）
- `@/components/primitives/*` — UI 基础组件
- 被 `app/health/page.tsx` 与 `features/settings/sections/system/SystemSection.tsx` 使用
- 父模块 [`features/_ARCH.md`](../_ARCH.md)
