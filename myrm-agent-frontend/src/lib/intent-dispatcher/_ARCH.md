# lib/intent-dispatcher/

Slash/深链意图分发 schema、解析与执行（schema 纯函数；执行经动态 import 接应用 store）。

| 文件             | 职责                                                                               |
| ---------------- | ---------------------------------------------------------------------------------- |
| `schema.ts`      | 意图 payload Zod schema                                                            |
| `index.ts`       | 解析与路由门面（`dispatch` 返回成功态，支持接收页面层已解析 intent，避免重复解析）；OAuth 回调先验后写落 CP token 并建 Cloud 档案 |
| `schema.test.ts` | `/intent/*` 与 `myrmagent://` URL 解析回归（ask/chat 路由与非法路径拦截）          |
