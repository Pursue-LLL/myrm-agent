# lib/utils/

通用纯函数工具集（认证头、导出、剪贴板、Agent 映射等）。**无** React 组件。

按域单文件组织；新工具优先就近放 feature/lib 子目录，仅跨 3+ feature 复用才放此处。

子目录 `__tests__/` 覆盖高价值纯函数。

- `mcpConfigNormalizer.ts`：MCP transport/keepalive 语义归一化（`http` → `streamable_http`；`stdio` keepalive 清空）。
