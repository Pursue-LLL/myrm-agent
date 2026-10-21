# lib/utils/error-handling/

错误处理域子包：展示脱敏引擎、轻量客户端脱敏、技能错误映射与错误去重管理。**无** React 组件，全部纯函数与单例管理器。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/error-handling`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖脱敏与客户端清洗行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合四文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `errorRedactor.ts`：展示脱敏引擎 — `redactErrorMessage` / `redactErrorObject` 覆盖 API Key、Bearer Token、JWT、数据库 URI 密码、主目录路径与私有内网 IP，保障 Toast、API 响应解析与内联错误文本零凭据泄漏；`maskToken` 单体脱敏与 `REDACTION_MASK` 常量。
- `clientRedact.ts`：客户端轻量脱敏清洗 — `redactSensitiveClientText` 与 `containsSensitiveData` 覆盖 OpenAI/Anthropic 风格 API Keys、GitHub Tokens、AWS 密钥、PEM 私钥、JWT 签名凭据与键值对密码，防御单条消息与前端导出 CWE-312 敏感信息明文泄露。
- `skillErrorMapper.ts`：技能错误映射 — `mapSkillErrorToTranslationKey` 后端技术性错误关键词到翻译键的正则映射与 `getFriendlyErrorMessage` 用户友好文案构建。
- `errorManager.ts`：错误去重管理器 — 30 秒窗口内相同错误去重展示（errorCache Map 时间戳记录），提升用户体验。

## 依赖

- `@/lib/api`（POS: 前端 API 接入层）— ApiError 类型（`errorManager.ts` 消费）。
