# adaptive-grid/

## 架构概述

折叠屏/平板与多窗口异构设备弹性自适应分栏网格、TUI 等宽字符视口智能伸缩与多任务同屏协同驾驶舱。
彻底解决传统单一边界断点将折叠屏（8:7/4:3 展开态）硬切为桌面所导致的中间大面积黑边空白、手机横屏挤压、以及终端 PTY 字符折行错位问题。

## 文件清单

| 文件 | 职责 |
| --- | --- |
| `adaptiveGridTypes.ts` | 姿态、布局模式、视口指标、终端字符矩阵及组件 Props 契约类型 |
| `useAdaptiveDevicePosture.ts` | 动态检测窗口像素、宽高比及设备姿态（foldable-expanded, mobile-landscape, tablet, desktop），自适应映射黄金双栏或紧凑模式 |
| `AdaptiveMultiPanelGrid.tsx` | 弹性分栏网格组件：折叠屏展开态黄金双栏分屏（45% : 55%）、手机横屏超宽紧凑模式、单栏标签切换及可拖拽比例分隔条 |
| `useTerminalPtyAutoResize.ts` | TUI 字符终端无级尺寸重协商 Hook：基于 ResizeObserver 与等宽字符度量动态计算 cols / rows，防抖派发 PTY ioctl 尺寸重协商 |
| `index.ts` | 模块统一对外门面导出 |

## 依赖关系

- `next-intl`: 双语国际化支持（`adaptiveLayout` 命名空间）
- `lucide-react`: 零原生 emoji，全量使用 SVG 矢量图标
