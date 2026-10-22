# 设计规范驱动工件生成、框选微调与公网发布套件架构设计 (_ARCH.md)

## 1. 业务痛点与核心价值
对标豆包工作顺丰官网复刻直播与 `styles.refero.design` 业界先进设计范式，破解传统 Agent 生成网页应用的三大硬伤：
- **痛点 1（审美失控与提示词玄学）**：单纯依靠自然语言提示词“好看一点”无法精确约束现代设计系统。本模块引入 `DESIGN.md` 设计规范文件驱动机制，将色盘（Palette）、排版（Typography）、圆角间距（Geometry）等令牌化（Tokens），无需反复调词即可直出顶尖工业级网页；
- **痛点 2（修改无法指哪改哪）**：用户难以用自然语言向 Agent 精确描述想修改的某个局部节点。本模块提供“所见即所得元素审查框选器 (Visual Element Selector)”，鼠标悬停动态绘制高亮盒模型与尺寸选择器药丸，点击一键锁定 DOM 选择器并自动组装结构化微调 Prompt 回填到输入框；
- **痛点 3（应用无法一键对外分发）**：工件停留在本地沙箱中无法快捷展示。本模块提供“零配置一键公网发布”能力，生成带防伪安全水印与可自定义有效期（24小时/7天/永久）的公网短链，并支持一键撤销访问控制。

## 2. 状态机与架构拓扑
```
               ┌───────────────────────────────┐
               │    DESIGN.md 设计规范文件     │
               └───────────────┬───────────────┘
                               │ 解析令牌 (Design Tokens)
                               ▼
        ┌──────────────────────────────────────────────┐
        │        useVisualArtifactStudioStore          │
        │  - activeSpec: 切换规范 (Minimal/Apple/Neon) │
        │  - isInspectMode: 开启/关闭元素审查蒙层      │
        │  - selectedElement: 锁定 DOM 选择器与尺寸    │
        │  - promptBackfillText: 自动组装微调 Prompt   │
        │  - publicShares: 生成/撤销公网访问短链       │
        └───────┬──────────────────────────────┬───────┘
                │                              │
                ▼                              ▼
┌──────────────────────────────┐ ┌──────────────────────────────┐
│ VisualElementSelectorOverlay │ │       PublicShareModal       │
│ - 鼠标悬停高亮盒模型         │ │ - 零配置公网短链发布         │
│ - 点击锁定选择器与源码       │ │ - 有效期控制与一键撤销       │
└──────────────────────────────┘ └──────────────────────────────┘
```

## 3. 模块文件清单
- `designSpecTypes.ts`：设计令牌、元素元数据、公网分享与 Store 完整类型接口；
- `designSpecParser.ts`：Markdown 设计规范解析器、CSS 变量生成器与 3 套预置高审美规范；
- `useVisualArtifactStudioStore.ts`：Zustand 集中式状态管理，协调审查模式、Prompt 自动合成与分享链路；
- `VisualElementSelectorOverlay.tsx`：所见即所得元素审查蒙层，带盒模型高亮与尺寸药丸；
- `DesignSpecSelectorCard.tsx`：设计规范挑选卡片，支持色盘微缩预览与 DESIGN.md 源码展开；
- `PublicShareModal.tsx`：语义化 `<dialog open>` 零配置一键公网发布弹窗；
- `VisualArtifactStudioCard.tsx`：生产级主控制台卡片；
- `index.ts`：统一模块导出。
