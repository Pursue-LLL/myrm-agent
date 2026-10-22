# WeChat Article Preview Architecture (`wechat-preview`)

## 模块定位
负责微信公众号与社交全媒体智能排版、四大主题（经典绿标、极简科技、大厂严谨、人文艺术）内联样式编译、以及多设备（手机 375px / 平板 768px / 电脑 680px）即时高保真预览与一键富文本复制（Item 45 P0）。

## 文件职责清单

| 文件名 | 类型 | 职责说明 | 状态 |
| :--- | :--- | :--- | :--- |
| `wechatPreviewTypes.ts` | 类型 | 领域类型定义：DeviceViewportMode, WechatThemeId, WechatBlockStyles, WechatThemeConfig, MultiDeviceArticlePreviewerProps | ✅ |
| `wechatThemes.ts` | 预设与编译器 | 四大微信排版主题预设与 compileWechatInlineHtml 内联样式注入编译器 | ✅ |
| `useWechatPreviewStore.ts` | 状态库 | 视口模式（mobile/tablet/desktop）、主题切换、字号缩放及复制状态管理 | ✅ |
| `MultiDeviceArticlePreviewer.tsx` | 预览器组件 | 多设备高保真仿真外壳、顶部 HUD 工具栏、实时内联富文本渲染与一键剪贴板复制 | ✅ |
| `index.ts` | 门面 | 统一导出所有类型、主题工具、状态库与预览器组件 | ✅ |
| `_ARCH.md` | 文档 | 模块定位与架构清单 | ✅ |
