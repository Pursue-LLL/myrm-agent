# components/features/presentation/

演示文稿（PPT）生成套件：生成弹窗、幻灯片渲染、预览与下载。服务端契约见 `@/services/presentation`（`POST /presentation/generate`）。

| 文件                                 | 职责                                                                                                                                                   |
| ------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `index.ts`                           | 对外门面：导出下列 4 个组件及其 Props 类型                                                                                                             |
| `PresentationTrigger.tsx`            | 工具菜单入口与全局快捷键（`Alt/Option + Cmd/Ctrl + P`），开关生成弹窗；`showTrigger={false}` 时只保留弹窗与监听，由 `i18n/LocalizedProviders.tsx` 挂载 |
| `PresentationGeneratorModal.tsx`     | `<dialog>` 生成弹窗：主题、模板风格、页数、是否配图 → `generatePresentation`，成功后切换到预览                                                         |
| `PresentationSlidePreviewViewer.tsx` | 幻灯片预览：按钮与方向键翻页、全屏放映（ESC 退出）、演讲者备注折叠、下载（`getPresentationDownloadUrl`）                                               |
| `PresentationSlideCard.tsx`          | 16:9 幻灯片渲染器：`title_hero` / `two_column_comparison` / `three_card_flow` / `concept_illustration_focus` / `summary_action` 布局，支持缩略图模式   |
| `__tests__/*.test.tsx`               | 四个组件各一份回归：表单渲染与生成/失败/关闭流程、布局渲染、翻页/备注/放映、快捷键与点击开弹窗                                                         |
