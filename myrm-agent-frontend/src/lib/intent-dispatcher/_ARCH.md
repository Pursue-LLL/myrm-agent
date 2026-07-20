# lib/intent-dispatcher/

Slash/深链意图分发 schema 与解析（纯函数，无 React）。

| 文件 | 职责 |
|------|------|
| `schema.ts` | 意图 payload Zod schema |
| `index.ts` | 解析与路由门面（`dispatch` 返回成功态，支持接收页面层已解析 intent，避免重复解析） |
| `schema.test.ts` | `/intent/*` 与 `myrmagent://` URL 解析回归（ask/chat 路由与非法路径拦截） |
