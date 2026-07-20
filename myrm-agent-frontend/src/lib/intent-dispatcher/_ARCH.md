# lib/intent-dispatcher/

Slash/深链意图分发 schema 与解析（纯函数，无 React）。

| 文件 | 职责 |
|------|------|
| `schema.ts` | 意图 payload Zod schema |
| `index.ts` | 解析与路由门面 |
| `schema.test.ts` | `/intent/*` 与 `myrmagent://` URL 解析回归（ask/chat 路由与非法路径拦截） |
