# lib/utils/locale/

Locale 域子包：客户端 locale 读取与协商、多语言文本选择。**无** React 组件（localeText 操作 ReactNode 但不渲染组件）。

对外唯一门面为 `index.ts` barrel（`@/lib/utils/locale`）；组件层消费点一律经 barrel 取公开符号，不深路径引用内部构件。

`__tests__/` 覆盖 locale 读取与文本选择行为。

- `index.ts`：域门面 barrel — 显式导出清单聚合两文件公开符号，组件层统一导入入口；新增导出须同步本清单（漏加即 typecheck 断裂，编译器护栏）。
- `localeUtils.ts`：Locale 工具集 — NEXT_LOCALE_COOKIE_NAME cookie 常量、getClientLocale 客户端读取、normalizeLocaleForBackend 后端格式映射、parseLocaleQueryParam 营销参数解析、negotiateLocale RFC 7231 Accept-Language 协商、urlWithoutLocaleParam 参数剥离。
- `localeText.ts`：多语言文本选择 — selectLocalizedText 按 locale 选取文案、localizeReactNode 递归本地化 ReactNode 树（Fragment/元素/文本）。

## 依赖

- react（localeText ReactNode 遍历）。
- `@/i18n/config`（POS: i18n 配置）— Locale 类型与 locales 列表。
