# progress-steps/renderers/

进度步骤叶子内容渲染：终端、代码、文件路径、来源、查询项等。

| 文件 | 职责 |
|------|------|
| `LiveTerminal.tsx` | 流式终端输出；evicted badge（行数/大小）+ View Full Output |
| `CodeRenderer.tsx` / `EnhancedSyntaxHighlighter.tsx` | 代码高亮 |
| `FilePathRenderer.tsx` / `URLItemsRenderer.tsx` | 路径与链接 |
| `SourcesRenderer.tsx` / `QueryItemsRenderer.tsx` / `TextItemsRenderer.tsx` | 检索与文本块 |
| `SkillSelectRenderer.tsx` | 技能选择步骤 |
| `EvictedOutputDrawer.tsx` | UECD 超长输出抽屉：分页 `GET /files/evicted?offset&limit=500`；404 → expired UX（`data-testid=evicted-output-expired`）；**当前页**搜索/复制（跨页搜索需翻页）；移动/桌面响应式 |
