# theme/shared/

## 架构概述

主题域共享组件：被主题设置与 Theme Studio 共同消费的展示与编辑件。避免在两处重复实现同一交互。

## 文件清单

| 文件                             | 地位 | 职责                                               | I/O/P |
| -------------------------------- | ---- | -------------------------------------------------- | ----- |
| `ThemeProfilePicker.tsx`         | 核心 | 主题档案选择器                                     | ✅    |
| `ThemePresetGrid.tsx`            | 核心 | 预设主题网格                                       | ✅    |
| `ThemePackageImportSection.tsx`  | 核心 | `.myrmtheme` 包检视/导入（可选导出）               | ✅    |
| `ThemeMediaUploadField.tsx`      | 辅助 | 主题媒体资源上传字段                               | ✅    |
| `SystemFontPicker.tsx`           | 辅助 | 系统字体选择器                                     | ✅    |

## 依赖

- `@/store/*`、`@/services/*`、`@/components/primitives/*`
- 父模块 [`../_ARCH.md`](../_ARCH.md)
