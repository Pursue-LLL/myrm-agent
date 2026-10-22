# curated-developer-themes 架构自文档

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `curatedThemeTypes.ts` | 类型契约 | 定义精选暗色主题标识、语义化 Token 与终端 ANSI 调色盘契约 | ✅ 稳定 |
| `curatedThemePresets.ts` | 配置字典 | 提供 6 套工业级经典开发者高对比度暗色主题预设（Tokyo Night、Catppuccin、Gruvbox 等） | ✅ 稳定 |
| `useCuratedThemeStore.ts` | 状态机 | Zustand 主题切换状态机与零开销原生 DOM CSS 变量注入管理器 | ✅ 稳定 |
| `CuratedThemeMatrixPicker.tsx` | UI 组件 | 外观设置界面的主题调色盘卡片矩阵、对比度徽章与实时终端预览器 | ✅ 稳定 |
| `index.ts` | 模块入口 | 统一导出所有类型、预设与 UI 组件 | ✅ 稳定 |
