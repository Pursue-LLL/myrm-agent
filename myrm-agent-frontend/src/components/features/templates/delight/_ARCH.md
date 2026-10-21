# components/features/templates/delight 模块架构

---

## 架构概述

小白零门槛趣味创意灵感工坊与单文件自包含即席沙箱展示台（Item 40 P0）。
支持非程序员家人/新手零门槛使用预置生活趣味灵感脚手架（程序员生日烟花、纪念日倒计时、聚餐命运大转盘、星空心愿瓶、复古像素弹球等），提供全屏响应式单文件 iframe 沙箱沉浸展示、高对比度 SVG 移动端局域网扫码即玩体验，彻底打破传统智能体的专业壁垒。

---

## 文件清单

| 文件 | 地位 | 职责 |
|------|------|------|
| `delightTypes.ts` | 类型 | 领域类型定义：DelightCategory、DelightTemplateItem、SingleFileSandboxContractItem、SandboxValidationResultItem、DelightShowcaseState |
| `useDelightShowcaseStore.ts` | 状态 | Zustand 状态管理：模板分类拉取、详情查询、沙箱全屏打开/关闭、二维码弹窗状态 |
| `QuickDelightLane.tsx` | 组件 | EmptyChat 欢迎页的极简生活趣味灵感胶囊条，一键填入 Prompt 或唤起灵感工坊 |
| `DelightTemplateGalleryModal.tsx` | 组件 | 趣味灵感工坊全景卡片弹窗，支持 5 大生活分类 Tabs、模糊过滤、即席预览与立即制作 |
| `SingleFileSandboxShowcase.tsx` | 组件 | 自包含单文件工件全屏即席展示台，内置全屏响应式 iframe 沙箱、一键代码复制与纯 SVG 移动端扫码分享 |
| `index.ts` | 门面 | 聚合导出模块内组件与状态 Hook |
| `_ARCH.md` | 文档 | 模块架构描述与文件清单 |

---

## 依赖关系

- `lucide-react`（矢量图标）
- `next-intl`（国际化）
- `zustand`（前端状态管理）
- `/api/v1/chats/delight-templates` 与 `/api/v1/chats/{chat_id}/delight-sandbox/validate` 后端 API 路由
