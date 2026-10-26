# memory/mesh/

## 架构概述

三域认知网格（Three-Domain Memory Mesh）UI：把记忆按 User / Assistant / Task 三个认知域分组呈现，
支持域内条目下钻追溯，以及 Hermes 等外部记忆的零摩擦导入。

组件为纯展示与交互层，域划分、条目统计、下钻详情与迁移导入均经 `@/services/memory/domainMesh` 获取；
本目录不持有服务端契约，新增能力应下沉到该 service。

## 文案与错误呈现

- 所有面向用户的文案位于 `locales/*.json` 的 `memory.mesh.*` 命名空间（`panel` / `domains` / `categories` / `card` / `drillDown` / `migration`），
  组件内以静态 key 调用 `useTranslations` 获取，六种语言同步维护。
- API 返回的域、类别、记忆类型标识符经 `useMeshLabels` 映射为本地化名称（记忆类型复用 `memory.types.*`）；
  本版本不认识的标识符（如导入包带入的自定义类别）属于用户数据，按原样显示。
- 请求失败已由 `apiRequest` 统一上报；本目录组件只展示本地化的非技术提示（重试入口、导入失败文案），
  不展示原始错误文本与内部记忆 ID。导入接口在无法解析时仍返回成功状态码，因此成功条数为 0 时按失败处理，
  并保留弹窗与已粘贴文本。
- 图标：通用动作沿用 `lucide-react`；标题与溯源类图标使用 `@phosphor-icons/react`（`TreeStructure`、`Path`）。

## 文件清单

| 文件                        | 地位 | 职责                                                                                                 | I/O/P |
| --------------------------- | ---- | ---------------------------------------------------------------------------------------------------- | ----- |
| `MemoryDomainMeshPanel.tsx` | 核心 | 三域认知网格主看板（User/Assistant/Task 域划分、条目统计、精选摘要卡片、加载失败重试）               | ✅    |
| `DomainMeshCard.tsx`        | 组件 | 领域卡片呈现组件（域标识、高亮条目渲染与下钻详情触发）                                               | ✅    |
| `MemoryDrillDownDialog.tsx` | 组件 | 记忆下钻追溯弹窗（消费级 ToC 纯净化展示、核心摘要与长文本滚动防爆容器、一键内容复制）                | ✅    |
| `useMeshLabels.ts`          | 辅助 | 域、类别、记忆类型标识符 → 当前语言名称（未知标识符原样返回），域卡片与下钻弹窗共用                  | ✅    |
| `index.ts`                  | 桶   | 域内 barrel：仅供域外按目录导入网格组件                                                              | ✅    |

## 依赖

- `@/services/memory/domainMesh` — 三域概览、下钻详情与迁移导入
- `next-intl` — `memory.mesh.*` 与 `memory.types.*` 文案
- `@/components/primitives/*` — 基础 UI 原子
- 父模块 [`memory/_ARCH.md`](../_ARCH.md)

## 引用规范

- 域内引用用相对路径（如 `./DomainMeshCard`）。
- 域外消费可直接 `@/components/features/memory/mesh`：`scripts/check_barrel_exports.py` 对
  `src/components/features/**/index.ts` 放行，无需 whitelist 条目。
