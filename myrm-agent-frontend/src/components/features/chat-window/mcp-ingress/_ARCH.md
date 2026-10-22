# mcp-ingress 架构自文档

| 文件 | 类型 | 职责描述 | 状态 |
| :--- | :--- | :--- | :--- |
| `mcpIngressTypes.ts` | 类型契约 | 定义远程 MCP 协议、工具描述符、即时握手探针结果与装配 Payload | ✅ 稳定 |
| `useMcpIngressStore.ts` | 状态机 | 输入框智能链接正则嗅探、防抖异步探针调度与三级装配状态机 | ✅ 稳定 |
| `McpLinkMountCard.tsx` | UI 组件 | 会话流内嵌装配卡片，呈现安全合规标签、声明工具列表与三级一键热挂载 | ✅ 稳定 |
| `McpUrlSnifferBar.tsx` | UI 组件 | 输入框上方轻量嗅探胶囊，发现用户贴入服务链接时就地提供即时握手引导 | ✅ 稳定 |
| `index.ts` | 模块入口 | 统一导出所有契约、Hook 与组件 | ✅ 稳定 |
