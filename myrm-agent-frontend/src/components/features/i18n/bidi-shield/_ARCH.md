# Item 121: BidirectionalRtlAndTypographyShieldSuite 架构设计

## 1. 核心定位与业务价值
针对中东等全球化多语系用户（如阿拉伯语、希伯来语、波斯语、乌尔都语），解决当阿语文案与英文代码变量（如 `user_token`）、URL、数字及标点符号混合时，因传统硬编码物理方向样式导致的界面反向崩坏、光标跳错、标点倒置以及 Windows 桌面 DirectWrite 复杂文本字体乱码硬伤。

## 2. 核心架构与模块划分
- `bidiShieldTypes.ts`: 书写方向状态机（ltr/rtl/auto）、双向切片元数据（BidiSegment）、字体栈配置模型与典型测试预设。
- `bidiDetectorEngine.ts`: 纯算法双向文本探测与分段隔离引擎。基于 Unicode 强方向字符区段计算 RTL 占比与主导方向；通过正则将代码块、变量与 URL 安全切分为独立 LTR 隔离段。
- `useBidiShieldStore.ts`: Zustand 集中式状态管理。负责书写方向调度、自动检测开关、Windows 字体加固开关与预设用例加载。
- `BidiIsolatedText.tsx`: 声明式双向文本隔离渲染组件。利用 `<bdi>` 双向隔离标签与 `unicode-bidi: isolate`，全量结合 CSS 逻辑属性（`text-start`, `padding-inline-start`, `margin-inline-end` 等），实现零错位、零重叠。
- `BidiTypographyShieldCard.tsx`: 交互式测试与对比组件。提供普通未隔离 vs Bidi 隔离加固的双重视窗对比，支持实时输入与 Windows 字体栈动态验证。
- `index.ts`: 统一聚合导出出口。

## 3. 全球化与平台适配治理
- Windows 平台字体防御：内置 `WINDOWS_RTL_SAFE_FONT_STACK`（Segoe UI, Tahoma, Noto Sans Arabic, Amiri 等），兜底 DirectWrite 复杂连字字形渲染；
- 全面淘汰物理方向 CSS 类（`pl-*` / `pr-*` / `ml-*` / `mr-*` / `left-*` / `right-*`），采用现代 CSS 逻辑属性保障 RTL 语系下自适应镜像对齐。
