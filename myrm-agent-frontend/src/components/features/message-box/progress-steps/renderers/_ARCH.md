# progress-steps/renderers/

进度步骤叶子内容渲染：终端、代码、文件路径、来源、查询项等。

| 文件 | 职责 |
|------|------|
| `LiveTerminal.tsx` | 流式终端输出 |
| `CodeRenderer.tsx` / `EnhancedSyntaxHighlighter.tsx` | 代码高亮 |
| `FilePathRenderer.tsx` / `URLItemsRenderer.tsx` | 路径与链接 |
| `SourcesRenderer.tsx` / `QueryItemsRenderer.tsx` / `TextItemsRenderer.tsx` | 检索与文本块 |
| `SkillSelectRenderer.tsx` | 技能选择步骤 |
| `EvictedOutputDrawer.tsx` | 超长输出抽屉 |
